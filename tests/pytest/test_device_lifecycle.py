"""Tests for the Device base class lifecycle interface."""

import pytest

from neurobooth_os.iout.device import Device, DeviceCapability, DeviceState
from neurobooth_os.iout.mock_device import MockRecordingDevice, MockStreamDevice


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


class TestStreamDeviceLifecycle:
    def test_initial_state(self):
        device = MockStreamDevice()
        assert device.state == DeviceState.CREATED
        assert not device.streaming

    def test_full_lifecycle(self):
        device = MockStreamDevice()
        assert device.state == DeviceState.CREATED

        device.configure()
        assert device.state == DeviceState.CONFIGURED

        device.connect()
        assert device.state == DeviceState.CONNECTED

        device.start()
        assert device.state == DeviceState.STARTED
        assert device.streaming

        device.stop()
        assert device.state == DeviceState.STOPPED
        assert not device.streaming

        device.disconnect()
        assert device.state == DeviceState.DISCONNECTED

    def test_start_ignores_filename(self):
        device = MockStreamDevice()
        device.connect()
        device.start(filename="should_be_ignored.txt")
        assert device.streaming

    def test_start_returns_empty_list(self):
        device = MockStreamDevice()
        device.connect()
        result = device.start()
        assert result == []

    def test_stop_is_idempotent(self):
        device = MockStreamDevice()
        device.connect()
        device.start()
        device.stop()
        device.stop()  # Should not raise
        assert device.stop_count == 1


class TestRecordingDeviceLifecycle:
    def test_start_requires_filename(self):
        device = MockRecordingDevice()
        device.connect()
        with pytest.raises(ValueError, match="filename"):
            device.start()

    def test_start_with_filename(self):
        device = MockRecordingDevice()
        device.connect()
        result = device.start(filename="test_video.avi")
        assert device.streaming
        assert device.last_filename == "test_video.avi"
        assert result == ["test_video.avi_mock.avi"]

    def test_ensure_stopped(self):
        device = MockRecordingDevice()
        device.connect()
        device.start(filename="test.avi")
        device.stop()
        device.ensure_stopped(timeout_seconds=5.0)
        assert device.ensure_stopped_called


# ---------------------------------------------------------------------------
# close() behavior
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_stops_streaming_device(self):
        device = MockStreamDevice()
        device.connect()
        device.start()
        assert device.streaming

        device.close()
        assert not device.streaming
        assert device.state == DeviceState.DISCONNECTED
        assert device.stop_count == 1

    def test_close_without_start_does_not_stop(self):
        device = MockStreamDevice()
        device.connect()
        device.close()
        assert device.state == DeviceState.DISCONNECTED
        assert device.stop_count == 0

    def test_close_recording_device(self):
        device = MockRecordingDevice()
        device.connect()
        device.start(filename="test.avi")
        device.close()
        assert not device.streaming
        assert device.state == DeviceState.DISCONNECTED


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_stream_device_capabilities(self):
        device = MockStreamDevice()
        assert device.has_capability(DeviceCapability.STREAM)
        assert not device.has_capability(DeviceCapability.RECORD)
        assert not device.has_capability(DeviceCapability.CAMERA_PREVIEW)
        assert not device.has_capability(DeviceCapability.WEARABLE)
        assert not device.has_capability(DeviceCapability.CALIBRATABLE)

    def test_recording_device_capabilities(self):
        device = MockRecordingDevice()
        assert device.has_capability(DeviceCapability.RECORD)
        assert device.has_capability(DeviceCapability.CAMERA_PREVIEW)
        assert not device.has_capability(DeviceCapability.STREAM)
        assert not device.has_capability(DeviceCapability.WEARABLE)

    def test_cannot_instantiate_base_class(self):
        with pytest.raises(TypeError):
            Device(MockStreamDevice()._mock_args)


# ---------------------------------------------------------------------------
# Common attributes
# ---------------------------------------------------------------------------


class TestCommonAttributes:
    def test_device_id_and_sensor_ids(self):
        device = MockStreamDevice(device_id="my_device", sensor_ids=["s1", "s2"])
        assert device.device_id == "my_device"
        assert device.sensor_ids == ["s1", "s2"]

    def test_outlet_id_is_unique(self):
        d1 = MockStreamDevice()
        d2 = MockStreamDevice()
        assert d1.outlet_id != d2.outlet_id

    def test_ensure_stopped_noop_on_stream_device(self):
        device = MockStreamDevice()
        device.connect()
        device.start()
        device.stop()
        device.ensure_stopped()  # Should not raise, inherited no-op
