"""Common device types and base class defining the standard device lifecycle."""

import logging
import uuid
from abc import ABC, abstractmethod
from enum import Enum, Flag, auto
from typing import Any, ByteString, ClassVar, List, Mapping, Optional

from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.log_manager import APP_LOG_NAME


class CameraPreviewException(Exception):
    """An exception raised when unable to capture a preview image/frame from a camera stream."""
    pass


class DeviceCapability(Flag):
    """Flags describing what a device can do. Devices may have multiple capabilities."""
    STREAM = auto()           # Continuous LSL streaming (mouse, mic, mbient)
    RECORD = auto()           # Records to file; start(filename) required (cameras, eyelink)
    CAMERA_PREVIEW = auto()   # Supports frame_preview()
    WEARABLE = auto()         # BLE/wireless; may disconnect unexpectedly, supports reconnect
    CALIBRATABLE = auto()     # Supports calibration (eyelink)
    RECORD_PER_TASK = auto()  # Recording is driven by the per-task lifecycle (cameras)
    RESETTABLE = auto()       # Participates in operator-triggered reset (mbient)
    SESSION_LEVEL = auto()    # Brought up regardless of whether any task references it (marker)


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
    def start(self, filename: Optional[str] = None) -> List[str]:
        """Begin data acquisition / streaming.

        Args:
            filename: Output file path. Required for devices with the RECORD
                capability; ignored by streaming-only devices.

        Returns:
            List of created file basenames (e.g. ``["task_flir.avi"]``).
            Streaming-only devices return an empty list.
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

    def bring_up(self, context: Mapping[str, Any]) -> Optional["Device"]:
        """Perform the full startup handshake and return self, or None to skip.

        Default: call ``connect()`` and, for pure STREAM devices, ``start()``.
        Devices with the ``RECORD`` capability defer ``start()`` to
        ``DeviceManager.start_recording_devices`` (per-task). Devices with
        optional connect (wearables, iPhone) or that depend on items in
        ``context`` (e.g. a PsychoPy window) should override this method.

        Args:
            context: Mapping of shared objects that some devices may need
                during start-up. The canonical key is ``"psychopy_window"``
                (used by EyeTracker); devices that do not need anything from
                context ignore the argument.

        Returns:
            ``self`` on success, or ``None`` if the device should be skipped
            (e.g. a wearable that failed to connect).
        """
        self.connect()
        if (self.has_capability(DeviceCapability.STREAM)
                and not self.has_capability(DeviceCapability.RECORD)):
            self.start()
        return self

    def on_task_reconnect(self) -> None:
        """Hook called by DeviceManager before each task starts.

        No-op by default. Override for wearables or other devices whose
        connection may have dropped between tasks.
        """
        pass

    def on_session_reset(self) -> bool:
        """Hook called when the operator requests a device reset.

        No-op by default; returns ``True`` to indicate nothing needed doing.
        Override for devices that support an operator-driven reset
        (e.g. Mbient ``reset_and_reconnect``).

        Returns:
            True on success, False otherwise.
        """
        return True

    def frame_preview(self) -> ByteString:
        """Return a single preview frame as encoded image bytes.

        Default implementation raises; override on devices that declare the
        ``CAMERA_PREVIEW`` capability.
        """
        raise CameraPreviewException(
            f"Device {self.device_id} does not support frame preview."
        )
