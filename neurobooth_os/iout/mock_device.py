"""Mock device implementations for testing the Device lifecycle interface."""

from typing import Optional

from neurobooth_os.iout.device import Device, DeviceCapability, DeviceState


class MockStreamDevice(Device):
    """A mock streaming device (like MouseStream or MicStream)."""

    capabilities = DeviceCapability.STREAM

    def __init__(self, device_id: str = "mock_stream", sensor_ids=None):
        # Build a minimal DeviceArgs-like object for testing
        self._mock_args = _MockDeviceArgs(device_id, sensor_ids or [])
        super().__init__(self._mock_args)
        self.start_count = 0
        self.stop_count = 0

    def connect(self) -> None:
        self.state = DeviceState.CONNECTED

    def start(self, filename: Optional[str] = None) -> None:
        self.streaming = True
        self.state = DeviceState.STARTED
        self.start_count += 1

    def stop(self) -> None:
        if self.streaming:
            self.streaming = False
            self.state = DeviceState.STOPPED
            self.stop_count += 1


class MockRecordingDevice(Device):
    """A mock recording device (like a camera or EyeTracker)."""

    capabilities = DeviceCapability.RECORD | DeviceCapability.CAMERA_PREVIEW

    def __init__(self, device_id: str = "mock_recorder", sensor_ids=None):
        self._mock_args = _MockDeviceArgs(device_id, sensor_ids or [])
        super().__init__(self._mock_args)
        self.last_filename: Optional[str] = None
        self.ensure_stopped_called = False

    def connect(self) -> None:
        self.state = DeviceState.CONNECTED

    def start(self, filename: Optional[str] = None) -> None:
        if filename is None:
            raise ValueError("Recording devices require a filename.")
        self.last_filename = filename
        self.streaming = True
        self.state = DeviceState.STARTED

    def stop(self) -> None:
        if self.streaming:
            self.streaming = False
            self.state = DeviceState.STOPPED

    def ensure_stopped(self, timeout_seconds: float = 10.0) -> None:
        self.ensure_stopped_called = True


class _MockDeviceArgs:
    """Minimal stand-in for DeviceArgs in tests."""

    def __init__(self, device_id: str, sensor_ids: list):
        self.device_id = device_id
        self.sensor_ids = sensor_ids
