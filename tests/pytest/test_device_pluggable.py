"""Tests for the pluggable device registration added in #696.

Covers the new surfaces: ``Device.bring_up`` default, the lifecycle hooks
(``on_task_reconnect`` / ``on_session_reset`` / ``frame_preview``),
``DeviceManager`` hook dispatch, capability-based ``camera_frame_preview``
gating, ``MarkerStreamDevice`` delegation, and each ``DeviceArgs`` subclass's
``device_class()`` wiring.

Backward-compat fallbacks (mouse string-match in ``DeviceArgs.instance_device_class``,
legacy ``marker_stream()`` function, ``CameraPreviewer`` shim) are intentionally
not tested — they are scheduled for removal in #708.
"""

import logging
from unittest.mock import MagicMock

import pytest

from neurobooth_os.iout.device import (
    CameraPreviewException,
    DeviceCapability,
    DeviceState,
)
from neurobooth_os.iout.lsl_streamer import DeviceManager
from neurobooth_os.iout.mock_device import MockRecordingDevice, MockStreamDevice


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dm():
    """DeviceManager with __init__ bypassed.

    __init__ validates node_name against SERVER_ASSIGNMENTS (loaded from the
    user's config at module import). Bypassing it keeps these tests independent
    of any particular deployment's server assignments.
    """
    manager = DeviceManager.__new__(DeviceManager)
    manager.logger = logging.getLogger('test_device_pluggable')
    manager.streams = {}
    manager.assigned_devices = []
    manager.marker_stream = False
    return manager


# ---------------------------------------------------------------------------
# Device.bring_up default behavior
# ---------------------------------------------------------------------------


class TestBringUpDefault:
    def test_stream_only_device_connects_and_starts(self):
        device = MockStreamDevice()
        result = device.bring_up({})
        assert result is device
        assert device.streaming
        assert device.start_count == 1
        assert device.state == DeviceState.STARTED

    def test_recording_device_connects_but_does_not_start(self):
        """RECORD devices defer start() to DeviceManager.start_recording_devices."""
        device = MockRecordingDevice()
        result = device.bring_up({})
        assert result is device
        assert not device.streaming
        assert device.state == DeviceState.CONNECTED

    def test_unused_context_keys_are_ignored(self):
        device = MockStreamDevice()
        device.bring_up({"psychopy_window": MagicMock(), "extra": 42})
        assert device.streaming


# ---------------------------------------------------------------------------
# Device.frame_preview default
# ---------------------------------------------------------------------------


class TestFramePreviewDefault:
    def test_device_without_override_raises(self):
        device = MockStreamDevice()
        with pytest.raises(CameraPreviewException):
            device.frame_preview()

    def test_capability_flag_alone_does_not_provide_implementation(self):
        """CAMERA_PREVIEW advertises support but the subclass must still override.

        MockRecordingDevice declares CAMERA_PREVIEW yet does not override
        frame_preview, so it exercises the base default.
        """
        device = MockRecordingDevice()
        with pytest.raises(CameraPreviewException):
            device.frame_preview()


# ---------------------------------------------------------------------------
# Device.on_task_reconnect / on_session_reset defaults
# ---------------------------------------------------------------------------


class TestLifecycleHookDefaults:
    def test_on_task_reconnect_is_noop(self):
        MockStreamDevice().on_task_reconnect()  # must not raise

    def test_on_session_reset_returns_true(self):
        assert MockStreamDevice().on_session_reset() is True


# ---------------------------------------------------------------------------
# DeviceManager hook dispatch
# ---------------------------------------------------------------------------


class TestDeviceManagerHooks:
    def test_reconnect_for_task_calls_hook_on_every_device(self, dm):
        d1 = MockStreamDevice(device_id='d1')
        d2 = MockStreamDevice(device_id='d2')
        d1.on_task_reconnect = MagicMock()
        d2.on_task_reconnect = MagicMock()
        dm.streams = {'d1': d1, 'd2': d2}

        dm.reconnect_for_task()

        d1.on_task_reconnect.assert_called_once()
        d2.on_task_reconnect.assert_called_once()

    def test_reconnect_for_task_skips_non_device_streams(self, dm):
        device = MockStreamDevice()
        device.on_task_reconnect = MagicMock()
        dm.streams = {'device': device, 'raw_outlet': object()}

        dm.reconnect_for_task()  # must not raise on raw_outlet

        device.on_task_reconnect.assert_called_once()

    def test_reset_devices_only_calls_resettable_devices(self, dm):
        """reset_devices must filter by RESETTABLE so the operator's UI only
        shows devices that actually performed a reset (today: Mbients).
        """
        resettable = MockStreamDevice(device_id='resettable')
        resettable.capabilities = (
            MockStreamDevice.capabilities | DeviceCapability.RESETTABLE
        )
        resettable.on_session_reset = MagicMock(return_value=True)

        plain = MockStreamDevice(device_id='plain')
        plain.on_session_reset = MagicMock(return_value=True)

        dm.streams = {'resettable': resettable, 'plain': plain}

        result = dm.reset_devices()

        assert result == {'resettable': True}
        plain.on_session_reset.assert_not_called()

    def test_reset_devices_collects_return_values(self, dm):
        d1 = MockStreamDevice(device_id='d1')
        d2 = MockStreamDevice(device_id='d2')
        for d, ok in ((d1, True), (d2, False)):
            d.capabilities = MockStreamDevice.capabilities | DeviceCapability.RESETTABLE
            d.on_session_reset = MagicMock(return_value=ok)
        dm.streams = {'d1': d1, 'd2': d2}

        assert dm.reset_devices() == {'d1': True, 'd2': False}

    def test_reset_devices_skips_non_device_streams(self, dm):
        device = MockStreamDevice()
        device.capabilities = MockStreamDevice.capabilities | DeviceCapability.RESETTABLE
        dm.streams = {'device': device, 'raw_outlet': object()}

        result = dm.reset_devices()

        assert list(result.keys()) == ['device']


# ---------------------------------------------------------------------------
# camera_frame_preview capability gating
# ---------------------------------------------------------------------------


class TestCameraFramePreviewGating:
    def test_missing_device_id_raises(self, dm):
        with pytest.raises(CameraPreviewException, match='unavailable'):
            dm.camera_frame_preview('missing')

    def test_device_without_capability_raises(self, dm):
        device = MockStreamDevice(device_id='plain')  # STREAM only, no CAMERA_PREVIEW
        dm.streams = {'plain': device}
        with pytest.raises(CameraPreviewException, match='not a valid preview'):
            dm.camera_frame_preview('plain')

    def test_non_device_stream_raises(self, dm):
        dm.streams = {'raw': object()}
        with pytest.raises(CameraPreviewException, match='not a valid preview'):
            dm.camera_frame_preview('raw')

    def test_forwards_to_device_when_capability_present(self, dm):
        device = MockRecordingDevice()  # declares CAMERA_PREVIEW
        device.frame_preview = MagicMock(return_value=b'PNG-bytes')
        dm.streams = {'cam': device}

        assert dm.camera_frame_preview('cam') == b'PNG-bytes'
        device.frame_preview.assert_called_once()


# ---------------------------------------------------------------------------
# MarkerStreamDevice lifecycle and delegation
# ---------------------------------------------------------------------------


class TestMarkerStreamDevice:
    def test_identity(self):
        from neurobooth_os.iout.marker import MarkerStreamDevice

        device = MarkerStreamDevice()
        assert device.device_id == MarkerStreamDevice.DEVICE_ID == 'marker'
        assert device.sensor_ids == ['marker']
        assert device.has_capability(DeviceCapability.STREAM)

    def test_push_sample_forwards_to_outlet(self):
        from neurobooth_os.iout.marker import MarkerStreamDevice

        device = MarkerStreamDevice()
        device.outlet = MagicMock()

        device.push_sample(["hello"])

        device.outlet.push_sample.assert_called_once_with(["hello"])

    def test_start_transitions_state(self):
        from neurobooth_os.iout.marker import MarkerStreamDevice

        device = MarkerStreamDevice()
        device.start()

        assert device.streaming
        assert device.state == DeviceState.STARTED

    def test_stop_releases_outlet_and_clears_state(self):
        from neurobooth_os.iout.marker import MarkerStreamDevice

        class _Outlet:
            """MagicMock doesn't auto-provide __del__, so use a real class."""
            def __init__(self) -> None:
                self.del_called = False

            def __del__(self) -> None:
                self.del_called = True

        outlet = _Outlet()
        device = MarkerStreamDevice()
        device.outlet = outlet
        device.streaming = True

        device.stop()

        assert not device.streaming
        assert device.state == DeviceState.STOPPED
        assert device.outlet is None
        assert outlet.del_called


# ---------------------------------------------------------------------------
# DeviceArgs subclass device_class() wiring
# ---------------------------------------------------------------------------


class TestDeviceArgsClassRegistry:
    """Each DeviceArgs subclass resolves to the correct concrete Device.

    These are the primary path; the legacy mouse string-match fallback in the
    base class is intentionally not tested (tracked for removal in #708).
    """

    def test_mic_yeti_args(self):
        from neurobooth_os.iout.stim_param_reader import MicYetiDeviceArgs
        from neurobooth_os.iout.microphone import MicStream
        assert MicYetiDeviceArgs.device_class() is MicStream

    def test_eyelink_args(self):
        from neurobooth_os.iout.stim_param_reader import EyelinkDeviceArgs
        from neurobooth_os.iout.eyelink_tracker import EyeTracker
        assert EyelinkDeviceArgs.device_class() is EyeTracker

    def test_iphone_args(self):
        from neurobooth_os.iout.stim_param_reader import IPhoneDeviceArgs
        from neurobooth_os.iout.iphone import IPhone
        assert IPhoneDeviceArgs.device_class() is IPhone

    def test_flir_args(self):
        from neurobooth_os.iout.stim_param_reader import FlirDeviceArgs
        from neurobooth_os.iout.flir_cam import VidRec_Flir
        assert FlirDeviceArgs.device_class() is VidRec_Flir

    def test_intel_args(self):
        from neurobooth_os.iout.stim_param_reader import IntelDeviceArgs
        from neurobooth_os.iout.camera_intel import VidRec_Intel
        assert IntelDeviceArgs.device_class() is VidRec_Intel

    def test_webcam_args(self):
        from neurobooth_os.iout.stim_param_reader import WebcamDeviceArgs
        from neurobooth_os.iout.webcam import VidRec_Webcam
        assert WebcamDeviceArgs.device_class() is VidRec_Webcam

    def test_mbient_args(self):
        from neurobooth_os.iout.stim_param_reader import MbientDeviceArgs
        from neurobooth_os.iout.mbient import Mbient
        assert MbientDeviceArgs.device_class() is Mbient

    def test_mouse_args(self):
        from neurobooth_os.iout.stim_param_reader import MouseDeviceArgs
        from neurobooth_os.iout.mouse_tracker import MouseStream
        assert MouseDeviceArgs.device_class() is MouseStream


# ---------------------------------------------------------------------------
# RECORD_PER_TASK capability assignments
# ---------------------------------------------------------------------------


class TestRecordPerTaskAssignment:
    """Cameras (started per-task) declare RECORD_PER_TASK; EyeTracker does not.

    This replaces the old ``RECORD and not CALIBRATABLE`` heuristic in
    ``_get_camera_devices`` / ``reconnect_streams``.
    """

    def test_flir_has_record_per_task(self):
        from neurobooth_os.iout.flir_cam import VidRec_Flir
        assert DeviceCapability.RECORD_PER_TASK in VidRec_Flir.capabilities

    def test_webcam_has_record_per_task(self):
        from neurobooth_os.iout.webcam import VidRec_Webcam
        assert DeviceCapability.RECORD_PER_TASK in VidRec_Webcam.capabilities

    def test_intel_has_record_per_task(self):
        from neurobooth_os.iout.camera_intel import VidRec_Intel
        assert DeviceCapability.RECORD_PER_TASK in VidRec_Intel.capabilities

    def test_iphone_has_record_per_task(self):
        from neurobooth_os.iout.iphone import IPhone
        assert DeviceCapability.RECORD_PER_TASK in IPhone.capabilities

    def test_eyetracker_excludes_record_per_task(self):
        from neurobooth_os.iout.eyelink_tracker import EyeTracker
        assert DeviceCapability.RECORD_PER_TASK not in EyeTracker.capabilities
        assert DeviceCapability.CALIBRATABLE in EyeTracker.capabilities


class TestResettableAssignment:
    """Only Mbient declares RESETTABLE — the capability exists so the operator
    "Reset" result lists only devices that actually performed a reset.
    """

    def test_mbient_has_resettable(self):
        from neurobooth_os.iout.mbient import Mbient
        assert DeviceCapability.RESETTABLE in Mbient.capabilities

    def test_cameras_are_not_resettable(self):
        from neurobooth_os.iout.flir_cam import VidRec_Flir
        from neurobooth_os.iout.webcam import VidRec_Webcam
        from neurobooth_os.iout.camera_intel import VidRec_Intel
        for cls in (VidRec_Flir, VidRec_Webcam, VidRec_Intel):
            assert DeviceCapability.RESETTABLE not in cls.capabilities

    def test_eyetracker_is_not_resettable(self):
        from neurobooth_os.iout.eyelink_tracker import EyeTracker
        assert DeviceCapability.RESETTABLE not in EyeTracker.capabilities
