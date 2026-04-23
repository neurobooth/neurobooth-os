import logging
import os
import threading
from neurobooth_os.iout.stim_param_reader import DeviceArgs, TaskArgs
from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os import config
from typing import Any, Dict, List, Mapping, ByteString, Optional, Type
from concurrent.futures import ThreadPoolExecutor, as_completed

import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.device import (
    Device, DeviceCapability, CameraPreviewException,
)
from neurobooth_os.msg.messages import DeviceInitialization, Request


config.load_config(validate_paths=False)
SERVER_ASSIGNMENTS: Dict[str, List[str]] = {}
for _i, _acq in enumerate(config.neurobooth_config.acquisition):
    SERVER_ASSIGNMENTS[f'acquisition_{_i}'] = _acq.devices
SERVER_ASSIGNMENTS['presentation'] = config.neurobooth_config.presentation.devices
SERVER_ASSIGNMENTS['control'] = config.neurobooth_config.control.devices


N_ASYNC_THREADS: int = 3
ASYNC_STARTUP: List[str] = []  # Device IDs whose bring_up runs concurrently in the thread pool.


class DeviceNotFoundException(Exception):
    """Exception raised when a given device ID cannot be found."""
    pass


def get_device_assignment(device_id: str) -> str:
    """Return the server a device is assigned to.

    Args:
        device_id: The ID of the device.

    Returns:
        The full name of the assigned server.

    Raises:
        DeviceNotFoundException: If the device is not in any server's assignment list.
    """
    for server_name, device_list in SERVER_ASSIGNMENTS.items():
        if device_id in device_list:
            return server_name
    raise DeviceNotFoundException(f'{device_id} is not assigned to any server.')


def is_device_assigned(device_id: str, server_name: str) -> bool:
    """Check whether a device is assigned to a particular server.

    When ``server_name`` is ``'acquisition'``, all indexed acquisition servers
    (``acquisition_0``, ``acquisition_1``, ...) are checked.

    Args:
        device_id: The ID of the device.
        server_name: The name of the server (e.g., ``'acquisition_0'``,
            ``'presentation'``, or the generic ``'acquisition'``).

    Returns:
        True if the device is assigned to the server.
    """
    if server_name in SERVER_ASSIGNMENTS:
        return device_id in SERVER_ASSIGNMENTS[server_name]
    if server_name == 'acquisition':
        return any(
            device_id in devices
            for key, devices in SERVER_ASSIGNMENTS.items()
            if key.startswith('acquisition_')
        )
    return False


# --------------------------------------------------------------------------------
# Handle the device life cycle
# --------------------------------------------------------------------------------
class DeviceManager:
    def __init__(self, node_name: str):
        self.logger = logging.getLogger(APP_LOG_NAME)
        self.streams: Dict[str, Any] = {}

        if node_name not in SERVER_ASSIGNMENTS:
            raise ValueError(f'Unrecognized node name ({node_name}) given to device manger!')
        self.assigned_devices = SERVER_ASSIGNMENTS[node_name]
        self.logger.debug(f'Devices assigned to {node_name}: {self.assigned_devices}')

        self.marker_stream = node_name in ['presentation']

    def create_streams(self, win=None, task_params=None) -> None:
        """Initialize devices and LSL streams for this node's assigned devices.

        Each device's startup lifecycle is driven by its ``Device.bring_up``
        override, so this method stays device-type-agnostic: it looks up the
        ``Device`` class from the ``DeviceArgs`` subclass, instantiates it,
        and hands it a shared ``context`` dict.

        Args:
            win: PsychoPy window (required for EyeTracker on the presentation node).
            task_params: Mapping of task IDs to TaskArgs. Used to determine which
                devices are needed across all tasks in the collection.
        """
        context: Mapping[str, Any] = {"psychopy_window": win}

        if self.marker_stream:
            from neurobooth_os.iout.marker import MarkerStreamDevice
            self.logger.debug('Device Manager Starting: marker')
            marker = MarkerStreamDevice()
            marker.connect()
            marker.start()
            self.streams[MarkerStreamDevice.DEVICE_ID] = marker

        register_lock = threading.Lock()

        def start_and_register_device(device_args: DeviceArgs) -> None:
            device_id = device_args.device_id
            self.logger.debug(f'Device Manager Starting: {device_id}')
            self.logger.debug(f'Device Manager Starting with args: {device_args}')
            device_cls: Type[Device] = device_args.instance_device_class()
            device = device_cls(device_args).bring_up(context)
            if device is None:
                self.logger.warning(f'Device Manager Failed to Start: {device_id}')
                return
            with register_lock:
                self.streams[device_id] = device

        with ThreadPoolExecutor(max_workers=N_ASYNC_THREADS) as executor:
            futures = []
            kwargs: Dict[str, DeviceArgs] = DeviceManager._get_unique_devices(task_params)
            for device_key, device_args in kwargs.items():
                if device_key not in self.assigned_devices:
                    continue
                if device_key in ASYNC_STARTUP:
                    futures.append(executor.submit(start_and_register_device, device_args))
                else:  # Run sequentially if not specified as async
                    start_and_register_device(device_args)

            for f in as_completed(futures):
                f.result()  # Raise errors that occur asynchronously

        self.logger.info(f'LOADED DEVICES: {list(self.streams.keys())}')

    @staticmethod
    def _get_unique_devices(task_params: Dict[str, TaskArgs]) -> Dict[str, DeviceArgs]:
        """Collect the unique set of DeviceArgs across all tasks.

        Args:
            task_params: Mapping of task IDs to TaskArgs for the collection.

        Returns:
            Mapping of device IDs to DeviceArgs, deduplicated across tasks.
        """
        kwarg_devs = task_params
        devices = {}
        for task in kwarg_devs.values():
            for device in task.device_args:
                devices[device.device_id] = device
        return devices

    # ---- Generic capability-based device queries ----

    def _is_device(self, stream: Any) -> bool:
        """Check if a stream object is a Device subclass."""
        return isinstance(stream, Device)

    def get_devices_with_capability(
        self,
        cap: DeviceCapability,
        task_devices: List[DeviceArgs] = None,
    ) -> Dict[str, Device]:
        """Return devices that have a given capability.

        Args:
            cap: The capability to filter by.
            task_devices: If provided, only return devices whose IDs appear in this list.
        """
        device_ids = {dev.device_id for dev in task_devices} if task_devices else None
        return {
            name: stream
            for name, stream in self.streams.items()
            if self._is_device(stream)
            and stream.has_capability(cap)
            and (device_ids is None or name in device_ids)
        }

    # ---- Recording device lifecycle ----

    def _get_camera_devices(self, task_devices: List[DeviceArgs]) -> List[Device]:
        """Return per-task recording devices (cameras) for the given task.

        Selects devices whose recording is driven by the task lifecycle via the
        ``RECORD_PER_TASK`` capability. EyeTracker declares ``RECORD`` but not
        ``RECORD_PER_TASK``, so it is excluded here (it is managed by the
        presentation server during initialization).
        """
        return list(self.get_devices_with_capability(
            DeviceCapability.RECORD_PER_TASK, task_devices
        ).values())

    def start_recording_devices(self, filename: str, fname: str,
                                 task_devices: List[DeviceArgs],
                                 log_task_id: Optional[str] = None) -> Dict[str, List[str]]:
        """Start camera recording devices in parallel for the given task.

        Writes log_sensor_file rows immediately (paths only, NULL timing)
        when log_task_id is provided, so files can be tracked even if the
        session crashes or is cancelled before XDF post-processing runs.

        Args:
            filename: Full output path prefix, passed to each device's ``start()``.
            fname: Unique per-run identifier (``{session_name}_{tsk_start_time}_{task_id}``),
                embedded in the basenames returned by each device.
            task_devices: Devices required by the current task.
            log_task_id: Pre-created log_task row ID from STM. When None, the
                early write is skipped and the XDF split's INSERT fallback
                handles registration later (no video paths, canary warning).

        Returns:
            Mapping of stream name to list of created file basenames.
        """
        cameras = self._get_camera_devices(task_devices)
        all_files: Dict[str, List[str]] = {}
        device_files: List[tuple] = []  # [(device, basenames), ...] for DB registration
        if not cameras:
            return all_files
        with ThreadPoolExecutor(max_workers=len(cameras)) as executor:
            futures = {executor.submit(device.start, filename): device for device in cameras}
            for future, device in futures.items():
                try:
                    created = future.result()
                    if created:
                        stream_name = getattr(device, 'streamName', None)
                        if stream_name:
                            all_files[stream_name] = created
                            device_files.append((device, created))
                except Exception as e:
                    self.logger.exception(e)
        if log_task_id is not None and device_files:
            self._register_sensor_files(log_task_id, filename, device_files)
        return all_files

    def _register_sensor_files(self, log_task_id: str, filename: str,
                               device_files: List[tuple]) -> None:
        """Write log_sensor_file rows for files just created by device.start().

        Each row captures log_task_id, device_id, sensor_id and the file paths
        (video basenames). Timing fields are left NULL; they will be populated
        by the XDF post-processing step.

        Failures are logged but not raised — the recording must continue even
        if the registration fails. The XDF split's INSERT fallback handles the
        missing row later.
        """
        try:
            from neurobooth_terra import Table
            from neurobooth_os.iout.split_xdf import LOG_SENSOR_COLUMNS
            session_folder = os.path.basename(os.path.dirname(filename))
            conn = meta.get_database_connection()
            try:
                table = Table("log_sensor_file", conn=conn)
                for device, basenames in device_files:
                    sensor_file_paths = [f'{session_folder}/{b}' for b in basenames]
                    pg_array = '{' + ', '.join(sensor_file_paths) + '}'
                    device_id = device.device_id
                    sensor_ids = device.sensor_ids or []
                    for sensor_id in sensor_ids:
                        table.insert_rows(
                            [(log_task_id, None, None, None, None,
                              device_id, sensor_id, pg_array)],
                            cols=LOG_SENSOR_COLUMNS,
                        )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            self.logger.critical(
                f"Early log_sensor_file write failed for log_task_id={log_task_id}: {e}")

    def stop_recording_devices(self, task_devices: List[DeviceArgs]) -> None:
        """Stop camera recording devices and wait for them to finish.

        Args:
            task_devices: Devices required by the current task.
        """
        cameras = self._get_camera_devices(task_devices)
        for device in cameras:  # Signal cameras to stop
            device.stop()
        for device in cameras:  # Wait for cameras to actually stop
            device.ensure_stopped(10)

    def get_calibration_device(self) -> Optional[Device]:
        """Return the first device with the ``CALIBRATABLE`` capability, if any.

        Today only EyeTracker declares ``CALIBRATABLE``; the "first wins" rule
        is explicit here so a second calibratable device would be a config
        issue rather than a silent bug.
        """
        calibratables = self.get_devices_with_capability(DeviceCapability.CALIBRATABLE)
        if calibratables:
            return next(iter(calibratables.values()))
        return None

    # ---- Session-level hooks ----

    def reconnect_for_task(self) -> None:
        """Call ``on_task_reconnect`` on every Device-backed stream.

        Devices override this hook when they need per-task recovery (e.g.,
        Mbient re-establishes dropped BLE links). Default is a no-op.
        """
        for stream in self.streams.values():
            if self._is_device(stream):
                stream.on_task_reconnect()

    def reset_devices(self) -> Dict[str, bool]:
        """Call ``on_session_reset`` on every Device-backed stream.

        Returns:
            Mapping of device name to whether the reset succeeded (defaults to
            ``True`` for devices without an override).
        """
        results: Dict[str, bool] = {}
        for name, stream in self.streams.items():
            if self._is_device(stream):
                results[name] = stream.on_session_reset()
        return results

    def camera_frame_preview(self, device_id: str) -> ByteString:
        """Capture a single preview frame from a camera device.

        Args:
            device_id: The ID of the camera device to capture from.

        Returns:
            PNG-encoded image bytes.

        Raises:
            CameraPreviewException: If the device is not found or does not support previews.
        """
        if device_id not in self.streams:
            raise CameraPreviewException(f'Device {device_id} unavailable.')

        camera = self.streams[device_id]
        if not self._is_device(camera) or not camera.has_capability(DeviceCapability.CAMERA_PREVIEW):
            raise CameraPreviewException(f'Device {device_id} is not a valid preview device.')

        return camera.frame_preview()

    def close_streams(self) -> None:
        """Close all device streams. Uses the standard Device.close() lifecycle method."""
        for stream_name, stream in self.streams.items():
            self.logger.debug(f'Device Manager Closing: {stream_name}')
            if self._is_device(stream):
                stream.close()
            else:
                stream.stop()

    def reconnect_streams(self) -> None:
        """Restart any non-camera streams that have stopped, and re-post DeviceInitialization messages.

        Skips devices with ``RECORD_PER_TASK`` because they are (re)started
        per-task via ``start_recording_devices()``. EyeTracker declares
        ``RECORD | CALIBRATABLE`` (not ``RECORD_PER_TASK``) and so is included
        here, matching pre-refactor behavior.
        """
        for stream_name, stream in self.streams.items():
            if self._is_device(stream) and stream.has_capability(DeviceCapability.RECORD_PER_TASK):
                continue

            if not stream.streaming:
                self.logger.debug(f'Device Manager Reconnecting: {stream_name}')
                stream.start()
            msg_body = DeviceInitialization(stream_name=stream_name, outlet_id=stream.outlet_id)
            msg = Request(source="lsl_streamer", destination="CTR", body=msg_body)
            meta.post_message(msg)
