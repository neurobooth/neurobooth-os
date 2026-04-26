"""Lifecycle tests for the synthetic iPhone mock.

These tests exercise ``MockIPhone`` end-to-end without any USB / socket
infrastructure or running iOS app.  Coverage:

- Handshake takes the device from ``#DISCONNECTED`` to ``#READY`` via the
  in-process transport (no ``USBMux``, no real socket).
- ``start`` -> recording -> ``stop`` -> ``ensure_stopped`` cycles through
  the state machine end-to-end.
- LSL ``_lsl_push_sample`` sees ``@STARTTIMESTAMP``, several
  ``@INPROGRESSTIMESTAMP``, then ``@STOPTIMESTAMP``.
- ``frame_preview()`` returns the canned bytes the mock transport
  injects.
- The substitution registry is populated by importing
  ``stim_param_reader``.
"""

import time

import pytest

from neurobooth_os.iout import iphone as iphone_mod
from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.mock.mock_iphone import (
    _CANNED_PREVIEW_BYTES,
    MockIPhone,
)
from neurobooth_os.iout.stim_param_reader import (
    IPhoneDeviceArgs,
    IPhoneSensorArgs,
    MockIPhoneDeviceArgs,
)


SAMPLE_FPS = 30
RECORDING_WINDOW_SEC = 0.5


def _build_mock_args() -> MockIPhoneDeviceArgs:
    """Construct a ``MockIPhoneDeviceArgs`` with the minimum fields ``IPhone`` reads."""
    sensor = IPhoneSensorArgs.model_construct(
        sensor_id="iphone_sens_1",
        sample_rate=SAMPLE_FPS,
        notifyonframe=1,
        videoquality="high",
        usecamerafacing="back",
        brightness=50,
        lenspos=0.5,
    )
    return MockIPhoneDeviceArgs.model_construct(
        ENV_devices={},
        device_id="IPhone_dev_1",
        sensor_ids=["iphone_sens_1"],
        sensor_array=[sensor],
        arg_parser="iout.stim_param_reader.py::MockIPhoneDeviceArgs()",
    )


@pytest.fixture
def mock_args() -> MockIPhoneDeviceArgs:
    return _build_mock_args()


@pytest.fixture(autouse=True)
def _disable_lsl_and_messaging(monkeypatch):
    """Skip LSL outlet creation and silence ``post_message`` so tests don't need
    a real LSL or database backend.  ``IPhone`` uses ``DISABLE_LSL`` to
    bypass ``_create_outlet`` (which posts ``DeviceInitialization``) and to
    short-circuit ``_lsl_push_sample``; ``post_message`` is also reached
    via ``send_status_msg`` and ``panic``.
    """
    monkeypatch.setattr(iphone_mod, "DISABLE_LSL", True)
    monkeypatch.setattr(iphone_mod, "post_message", lambda msg: None)


class TestMockIPhoneLifecycle:

    def test_handshake_lands_in_ready(self, mock_args):
        device = MockIPhone(device_args=mock_args)
        try:
            assert device.connect() is True
            assert device.connected is True
            assert device.state == DeviceState.CONNECTED
            assert device._state == "#READY"
        finally:
            device.close()

    def test_start_stop_cycle(self, mock_args):
        device = MockIPhone(device_args=mock_args)
        try:
            assert device.connect() is True
            files = device.start("/tmp/task_obs_1")
            # IPhone.start strips the directory and appends "_IPhone".
            assert files == ["task_obs_1_IPhone.mov", "task_obs_1_IPhone.json"]
            assert device.streaming is True
            assert device._state == "#RECORDING"
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
            device.ensure_stopped(timeout_seconds=2)
            assert device._state == "#READY"
            assert device.streaming is False
        finally:
            device.close()

    def test_close_drives_state_to_disconnected(self, mock_args):
        device = MockIPhone(device_args=mock_args)
        device.connect()
        device.close()
        assert device.state == DeviceState.DISCONNECTED
        assert device._state == "#DISCONNECTED"
        assert device.connected is False
        assert device.streaming is False

    def test_close_after_recording_stops_stream_thread(self, mock_args):
        device = MockIPhone(device_args=mock_args)
        device.connect()
        device.start("/tmp/task_a")
        # Verify the transport's synthetic-stream thread is running.
        assert device.transport._stream_thread is not None
        assert device.transport._stream_thread.is_alive()
        device.close()
        # close() drains the thread via transport.close().
        assert (
            device.transport._stream_thread is None
            or not device.transport._stream_thread.is_alive()
        )


class TestMockIPhoneLSLFlow:

    def test_lsl_push_sample_sees_full_recording_sequence(
        self, mock_args, monkeypatch
    ):
        """During a recording the mock should drive @STARTTIMESTAMP,
        a stream of @INPROGRESSTIMESTAMP at the configured FPS, and
        @STOPTIMESTAMP — in that order — through ``_lsl_push_sample``.
        """
        device = MockIPhone(device_args=mock_args)
        captured_types = []

        def recorder(message):
            mt = message.get("MessageType", "")
            if mt in ("@STARTTIMESTAMP", "@INPROGRESSTIMESTAMP", "@STOPTIMESTAMP"):
                captured_types.append(mt)

        monkeypatch.setattr(device, "_lsl_push_sample", recorder)

        try:
            device.connect()
            device.start("/tmp/task_a")
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
            device.ensure_stopped(timeout_seconds=2)
        finally:
            device.close()

        assert captured_types, "Expected at least one timestamp sample"
        assert captured_types[0] == "@STARTTIMESTAMP"
        # @STOPTIMESTAMP is the last frame-related message; trailing
        # @INPROGRESSTIMESTAMP from the streaming thread shouldn't sneak
        # in after stop() because the transport's _end_streaming joins
        # the stream thread before queueing @STOPTIMESTAMP.
        assert "@STOPTIMESTAMP" in captured_types
        in_progress = sum(1 for t in captured_types if t == "@INPROGRESSTIMESTAMP")
        # 30 FPS * 0.5s = ~15; allow generous slack for jitter.
        assert in_progress >= 3, (
            f"Expected several @INPROGRESSTIMESTAMP messages; got {in_progress}"
        )

    def test_frame_preview_returns_canned_bytes(self, mock_args):
        device = MockIPhone(device_args=mock_args)
        try:
            device.connect()
            preview = device.frame_preview()
            assert preview == _CANNED_PREVIEW_BYTES
            assert len(preview) > 0
        finally:
            device.close()


class TestMockIPhoneRegistration:
    """Verify the substitution registry is wired up for IPhone."""

    def test_mock_iphone_is_registered(self):
        from neurobooth_os.iout.mock_substitution import MOCK_REGISTRY
        assert MOCK_REGISTRY.get(IPhoneDeviceArgs) is MockIPhoneDeviceArgs

    def test_device_class_resolves_to_mock(self):
        assert MockIPhoneDeviceArgs.device_class() is MockIPhone

    def test_apply_substitution_swaps_class(self):
        from neurobooth_os.iout.mock_substitution import apply_mock_substitution
        real = IPhoneDeviceArgs.model_construct(
            ENV_devices={},
            device_id="IPhone_dev_1",
            sensor_ids=["iphone_sens_1"],
            sensor_array=[],
            arg_parser="iout.stim_param_reader.py::IPhoneDeviceArgs()",
        )
        result = apply_mock_substitution(real, active={"IPhone"})
        assert isinstance(result, MockIPhoneDeviceArgs)
        assert result.device_id == "IPhone_dev_1"
