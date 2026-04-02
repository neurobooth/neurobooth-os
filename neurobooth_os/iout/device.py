"""Common device types and base class defining the standard device lifecycle."""

import logging
import uuid
from abc import ABC, abstractmethod
from enum import Enum, Flag, auto
from typing import ByteString, ClassVar, List, Optional

from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.log_manager import APP_LOG_NAME


class CameraPreviewException(Exception):
    """An exception raised when unable to capture a preview image/frame from a camera stream."""
    pass


class CameraPreviewer:
    def frame_preview(self) -> ByteString:
        """
        Retrieve a single frame from a camera.

        :returns: The raw data of the image/frame, or an empty byte string if an error occurs.
        """
        raise NotImplementedError()


class DeviceCapability(Flag):
    """Flags describing what a device can do. Devices may have multiple capabilities."""
    STREAM = auto()           # Continuous LSL streaming (mouse, mic, mbient)
    RECORD = auto()           # Records to file; start(filename) required (cameras, eyelink)
    CAMERA_PREVIEW = auto()   # Supports frame_preview()
    WEARABLE = auto()         # BLE/wireless; may disconnect unexpectedly, supports reconnect
    CALIBRATABLE = auto()     # Supports calibration (eyelink)


class DeviceState(Enum):
    """Coarse external-facing state of a device in its lifecycle."""
    CREATED = "created"
    CONFIGURED = "configured"
    CONNECTED = "connected"
    STARTED = "started"
    STOPPED = "stopped"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class Device(ABC):
    """Base class for all neurobooth-os devices.

    Defines a standard lifecycle with stages:
        configure -> connect -> start -> stop -> disconnect -> close

    Subclasses must implement ``start()`` and ``stop()``. All other lifecycle
    methods have no-op defaults and can be overridden as needed.

    Attributes:
        capabilities: Class-level flags declaring what this device can do.
        device_id: Unique identifier for the device.
        sensor_ids: List of sensor identifiers associated with the device.
        outlet_id: UUID used as the LSL outlet source ID.
        outlet: The LSL StreamOutlet (created during ``connect()``).
        streaming: Whether the device is currently streaming/recording.
        state: Current lifecycle state.
    """

    capabilities: ClassVar[DeviceCapability] = DeviceCapability(0)

    def __init__(self, device_args: Optional[DeviceArgs] = None) -> None:
        self.device_id: Optional[str] = device_args.device_id if device_args else None
        self.sensor_ids: Optional[List[str]] = device_args.sensor_ids if device_args else None
        self.outlet_id: str = str(uuid.uuid4())
        self.outlet = None  # Created in connect(); type varies by device
        self.streaming: bool = False
        self.state: DeviceState = DeviceState.CREATED
        self.logger = logging.getLogger(APP_LOG_NAME)

    def configure(self) -> None:
        """Set device parameters from config. No-op by default."""
        self.state = DeviceState.CONFIGURED

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to hardware and create LSL outlet."""
        ...

    @abstractmethod
    def start(self, filename: Optional[str] = None) -> None:
        """Begin data acquisition / streaming.

        Args:
            filename: Output file path. Required for devices with the RECORD
                capability; ignored by streaming-only devices.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop data acquisition / streaming."""
        ...

    def ensure_stopped(self, timeout_seconds: float = 10.0) -> None:
        """Wait for async stop to complete. No-op by default.

        Args:
            timeout_seconds: Maximum time to wait for the device to finish stopping.
        """
        pass

    def disconnect(self) -> None:
        """Release hardware connection. No-op by default."""
        self.state = DeviceState.DISCONNECTED

    def close(self) -> None:
        """Release all resources. Calls ``stop()`` then ``disconnect()`` by default."""
        if self.streaming:
            self.stop()
        self.disconnect()

    def has_capability(self, cap: DeviceCapability) -> bool:
        """Check whether this device has a given capability.

        Args:
            cap: The capability flag to check.

        Returns:
            True if the device has the capability.
        """
        return cap in self.capabilities
