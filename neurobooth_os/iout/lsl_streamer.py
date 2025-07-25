import logging
import threading
from neurobooth_os.iout.stim_param_reader import DeviceArgs, TaskArgs
from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os import config
from typing import Any, Dict, List, Callable, ByteString
from concurrent.futures import ThreadPoolExecutor, as_completed, wait

import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.device import CameraPreviewer, CameraPreviewException
from neurobooth_os.iout.mbient import Mbient
from neurobooth_os.msg.messages import DeviceInitialization, Request

# --------------------------------------------------------------------------------
# Wrappers for device setup procedures.
# TODO: Handle device setup calls and imports in a more standardized/extensible fashion!!!
# --------------------------------------------------------------------------------
def start_eyelink_stream(win, device_args):
    from neurobooth_os.iout.eyelink_tracker import EyeTracker
    return EyeTracker(win=win, device_args=device_args)


def start_mouse_stream(_, device_args):
    from neurobooth_os.iout.mouse_tracker import MouseStream
    device = MouseStream(device_args)
    device.start()
    return device


def start_mbient_stream(_, device_args):
    device = Mbient(device_args)
    if not device.prepare():
        return None
    device.start()
    return device


def start_intel_stream(_, device_args):
    from neurobooth_os.iout.camera_intel import VidRec_Intel
    return VidRec_Intel(device_args)


def start_flir_stream(_, device_args):
    from neurobooth_os.iout.flir_cam import VidRec_Flir
    return VidRec_Flir(device_args)


def start_webcam_stream(_, device_args):
    from neurobooth_os.iout.webcam import VidRec_Webcam
    return VidRec_Webcam(device_args)


def start_iphone_stream(_, device_args):
    from neurobooth_os.iout.iphone import IPhone
    device = IPhone(name="IPhoneFrameIndex", device_args=device_args)
    return device if device.prepare() else None


def start_yeti_stream(_, device_args):
    from neurobooth_os.iout.microphone import MicStream
    device = MicStream(device_args)
    device.start()
    return device


config.load_config()
acq_devices: List[str] = config.neurobooth_config.acquisition.devices
stm_devices: List[str] = config.neurobooth_config.presentation.devices
SERVER_ASSIGNMENTS: Dict[str, List[str]] = {
    'acquisition': acq_devices,
    'presentation':stm_devices,
}


N_ASYNC_THREADS: int = 3  # The maximum number of mbients on one machine
ASYNC_STARTUP: List[str] = [
    'Mbient_BK_1',
    'Mbient_LF_2',
    'Mbient_LH_2',
    'Mbient_RF_2',
    'Mbient_RH_2',
]


class DeviceNotFoundException(Exception):
    """Exception raised when a given device ID cannot be found."""
    pass


def get_device_assignment(device_id: str) -> str:
    """
    Return the server a device is assigned to. Raises a DeviceNotFoundException if the device is not found.
    :param device_id: The ID of the device.
    :return: The full name of the assigned server.
    """
    for server_name, device_list in SERVER_ASSIGNMENTS.items():
        if device_id in device_list:
            return server_name
    raise DeviceNotFoundException(f'{device_id} is not assigned to any server.')


def is_device_assigned(device_id: str, server_name: str) -> bool:
    """
    Check whether a device is assigned to a particular server.
    :param device_id: The ID of the device.
    :param server_name: The name of the server.
    :return: True if the device is assigned to a server, False otherwise.
    """
    return device_id in SERVER_ASSIGNMENTS[server_name]


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
        """
        Initialize devices and LSL streams.

        :param win: PsychoPy window
        :param task_params: task configuration parameters
        """
        if self.marker_stream:  # TODO: Handle the marker stream better
            from neurobooth_os.iout import marker_stream
            self.logger.debug(f'Device Manager Starting: marker')
            self.streams["marker"] = marker_stream()

        register_lock = threading.Lock()

        def start_and_register_device(device_args: DeviceArgs) -> None:
            device_id = device_args.device_id
            self.logger.debug(f'Device Manager Starting: {device_id}')
            self.logger.debug(f'Device Manager Starting with args: {device_args}')
            device_start_function: Callable = meta.str_fileid_to_eval(device_args.device_start_function)
            device = device_start_function(win, device_args)
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
    def _get_unique_devices(task_params: Dict) -> Dict[str, DeviceArgs]:
        """
        Fetch the DeviceArgs for each device used in the collection, eliminating any duplicates

        :param collection_id: Name of study collection.
        """
        # Get all tasks in collection
        kwarg_devs: Dict[str, TaskArgs] = task_params
        # Aggregate the devices used by the tasks
        devices = {}
        for task in kwarg_devs.values():
            for device in task.device_args:
                devices[device.device_id] = device
        return devices

    # TODO: The below device-specific calls should all be refactored so that devices can be generically handled
    # TODO: E.g., devices should be able to register handlers for lifecycle phases

    # TODO: the is_camera check should be based on an attribute of the DeviceArgs, not a check against
    #  a list of words, which requires updating code for every new camera
    @staticmethod
    def is_camera(stream_name: str) -> bool:
        """Test to see if a stream is a camera stream based on its name."""
        return stream_name.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone", "Webcam"]

    def get_camera_streams(self, task_devices: List[DeviceArgs]) -> List[Any]:
        device_ids = [dev.device_id for dev in task_devices]
        return [
            stream for stream_name, stream in self.streams.items()
            if DeviceManager.is_camera(stream_name) and stream_name in device_ids
        ]

    def get_mbient_streams(self) -> Dict[str, Any]:
        return {
            stream_name: stream for stream_name, stream in self.streams.items() if 'Mbient' in stream_name
        }

    def get_eyelink_stream(self):
        for stream_name, stream in self.streams.items():
            if 'Eyelink' in stream_name:
                return stream
        return None

    def start_cameras(self, filename: str, task_devices: List[DeviceArgs]) -> None:
        for stream in self.get_camera_streams(task_devices):
            try:
                stream.start(filename)
            except Exception as e:
                self.logger.exception(e)

    def stop_cameras(self, task_devices: List[DeviceArgs]):
        cameras = self.get_camera_streams(task_devices)
        for stream in cameras:  # Signal cameras to stop
            stream.stop()
        for stream in cameras:  # Wait for cameras to actually stop
            stream.ensure_stopped(10)

    def mbient_reconnect(self) -> None:
        from neurobooth_os.iout.mbient import Mbient
        Mbient.task_start_reconnect(list(self.get_mbient_streams().values()))

    def mbient_reset(self) -> Dict[str, bool]:
        """Reset mbient devices in parallel."""
        mbient_streams = self.get_mbient_streams()

        if len(mbient_streams) == 0:
            self.logger.debug('No mbients to reset.')
            return {}

        with ThreadPoolExecutor(max_workers=len(mbient_streams)) as executor:
            # Begin concurrent reset of devices
            reset_results = {
                stream_name: executor.submit(stream.reset_and_reconnect)
                for stream_name, stream in mbient_streams.items()
            }

            # Wait for resets to complete, then resolve the futures
            wait(reset_results.values())
            return {stream_name: result.result() for stream_name, result in reset_results.items()}

    def camera_frame_preview(self, device_id: str) -> ByteString:
        if device_id not in self.streams:
            raise CameraPreviewException(f'Device {device_id} unavailable.')

        camera = self.streams[device_id]
        if not isinstance(camera, CameraPreviewer):
            raise CameraPreviewException(f'Device {device_id} is not a valid preview device.')

        return camera.frame_preview()

    def close_streams(self) -> None:
        for stream_name, stream in self.streams.items():
            self.logger.debug(f'Device Manager Closing: {stream_name}')
            if DeviceManager.is_camera(stream_name):
                stream.close()
            else:
                stream.stop()

    def reconnect_streams(self):
        for stream_name, stream in self.streams.items():
            if DeviceManager.is_camera(stream_name):
                continue

            if not stream.streaming:
                self.logger.debug(f'Device Manager Reconnecting: {stream_name}')
                stream.start()
            msg_body = DeviceInitialization(stream_name=stream_name, outlet_id=stream.outlet_id)
            msg = Request(source="lsl_streamer", destination="CTR", body=msg_body)
            with meta.get_database_connection() as conn:
                meta.post_message(msg, conn)
