import logging
import threading
from neurobooth_os.iout import metadator as meta
from typing import Any, Dict, List, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, wait


# --------------------------------------------------------------------------------
# Wrappers for device setup procedures.
# TODO: Handle device setup calls and imports in a more standardized/extensible fashion!!!
# --------------------------------------------------------------------------------
def start_eyelink_stream(win, **device_args):
    from neurobooth_os.iout.eyelink_tracker import EyeTracker
    return EyeTracker(win=win, **device_args)


def start_mouse_stream(_, **device_args):
    from neurobooth_os.iout.mouse_tracker import MouseStream
    device = MouseStream(**device_args)
    device.start()
    return device


def start_mbient_stream(_, **device_args):
    from neurobooth_os.iout.mbient import Mbient
    device = Mbient(**device_args)
    if not device.prepare():
        return None
    device.start()
    return device


def start_mbient_mock_stream(_, **device_args):
    from neurobooth_os.mock.mock_device_streamer import MockMbient
    device = MockMbient(**device_args)
    device.start()
    return device


def start_intel_stream(_, **device_args):
    from neurobooth_os.iout.camera_intel import VidRec_Intel
    return VidRec_Intel(**device_args)


def start_intel_mock_stream(_, **device_args):
    from neurobooth_os.mock.mock_device_streamer import MockCamera
    return MockCamera(**device_args)


def start_flir_stream(_, **device_args):
    from neurobooth_os.iout.flir_cam import VidRec_Flir
    return VidRec_Flir(**device_args)


def start_iphone_stream(_, **device_args):
    from neurobooth_os.iout.iphone import IPhone
    device = IPhone(name="IPhoneFrameIndex", **device_args)
    return device if device.prepare() else None


def start_yeti_stream(_, **device_args):
    from neurobooth_os.iout.microphone import MicStream
    device = MicStream(**device_args)
    device.start()
    return device


# --------------------------------------------------------------------------------
# Device Configurations
# TODO: Server assignment and device setup should all be derived from config files!!!
# --------------------------------------------------------------------------------

SERVER_ASSIGNMENTS: Dict[str, List[str]] = {
    'acquisition': [
        'Intel_D455_1', 'Intel_D455_2', 'Intel_D455_3', 'FLIR_blackfly_1', 'IPhone_dev_1',
        'Mbient_BK_1', 'Mbient_LH_1', 'Mbient_LH_2', 'Mbient_RH_1', 'Mbient_RH_2',
        'Mic_Yeti_dev_1',
    ],
    'presentation': ['Eyelink_1', 'Mouse', 'Mbient_LF_1', 'Mbient_LF_2', 'Mbient_RF_2'],
    'dummy_acq': ['mock_Intel_1', 'mock_Mbient_1', 'mock_Mbient_2'],
    'dummy_stm': [],
}


DEVICE_START_FUNCS: Dict[str, Callable] = {
    'Eyelink_1': start_eyelink_stream,
    'FLIR_blackfly_1': start_flir_stream,
    'Intel_D455_1': start_intel_stream,
    'Intel_D455_2': start_intel_stream,
    'Intel_D455_3': start_intel_stream,
    'IPhone_dev_1': start_iphone_stream,
    'Mbient_BK_1': start_mbient_stream,
    'Mbient_LF_1': start_mbient_stream,
    'Mbient_LF_2': start_mbient_stream,
    'Mbient_LH_1': start_mbient_stream,
    'Mbient_LH_2': start_mbient_stream,
    'Mbient_RF_2': start_mbient_stream,
    'Mbient_RH_1': start_mbient_stream,
    'Mbient_RH_2': start_mbient_stream,
    'Mic_Yeti_dev_1': start_yeti_stream,
    'Mouse': start_mouse_stream,
    # ------------------------------
    'mock_Intel_1': start_intel_mock_stream,
    'mock_Mbient_1': start_mbient_mock_stream,
    'mock_Mbient_2': start_mbient_mock_stream,
}


N_ASYNC_THREADS: int = 3  # The maximum number of mbients on one machine
ASYNC_STARTUP: List[str] = [
    'Mbient_BK_1',
    'Mbient_LF_1',
    'Mbient_LF_2',
    'Mbient_LH_1',
    'Mbient_LH_2',
    'Mbient_RF_2',
    'Mbient_RH_1',
    'Mbient_RH_2',
]


# --------------------------------------------------------------------------------
# Handle the device life cycle
# --------------------------------------------------------------------------------
class DeviceManager:
    def __init__(self, node_name: str):
        self.logger = logging.getLogger('session')
        self.streams: Dict[str, Any] = {}

        if node_name not in SERVER_ASSIGNMENTS:
            raise ValueError(f'Unrecognized node name ({node_name}) given to device manger!')
        self.assigned_devices = SERVER_ASSIGNMENTS[node_name]
        self.logger.debug(f'Devices assigned to {node_name}: {self.assigned_devices}')

        self.marker_stream = node_name in ['presentation', 'dummy_stm']

    def create_streams(self, collection_id: str = "mvp_030", win=None, conn=None) -> None:
        """
        Initialize devices and LSL streams.

        :param collection_id: Name of study collection in the database.
        :param win: PsychoPy window
        :param conn: Connection to the database
        """
        if self.marker_stream:  # TODO: Handle the marker stream better
            from neurobooth_os.iout import marker_stream
            self.logger.debug(f'Device Manager Starting: marker')
            self.streams["marker"] = marker_stream()

        register_lock = threading.Lock()

        def start_and_register_device(device_key: str, device_args: Dict[str, Any]) -> None:
            self.logger.debug(f'Device Manager Starting: {device_key}')
            device = DEVICE_START_FUNCS[device_key](win, **device_args)
            if device is None:
                self.logger.warning(f'Device Manager Failed to Start: {device_key}')
                return
            with register_lock:
                self.streams[device_key] = device

        with ThreadPoolExecutor(max_workers=N_ASYNC_THREADS) as executor:
            futures = []
            for device_key, device_args in DeviceManager._get_device_kwargs(collection_id, conn).items():
                if device_key not in self.assigned_devices:
                    continue
                if device_key in ASYNC_STARTUP:
                    futures.append(executor.submit(start_and_register_device, device_key, device_args))
                else:  # Run sequentially if not specified as async
                    start_and_register_device(device_key, device_args)

            for f in as_completed(futures):
                f.result()  # Raise errors that occur asynchronously

        self.logger.info(f'LOADED DEVICES: {list(self.streams.keys())}')

    @staticmethod
    def _get_device_kwargs(collection_id: str, conn=None) -> Dict[str, Any]:
        """
        Fetch the keyword arguments for each device from the database.

        :param collection_id: Name of study collection in the database.
        :param win: PsychoPy window
        :param conn: Connection to the database
        """
        # Get params from all tasks
        kwarg_devs = meta.get_device_kwargs_by_task(collection_id, conn)

        # Get all device params from session
        kwarg_alldevs = {}
        for dc in kwarg_devs.values():
            kwarg_alldevs.update(dc)

        return kwarg_alldevs

    # TODO: The below device-specific calls should all be refactored so that devices can be generically handled
    # TODO: E.g., devices should be able to register handlers for lifecycle phases

    @staticmethod
    def is_camera(stream_name: str) -> bool:
        """Test to see if a stream is a camera stream based on its name."""
        return stream_name.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]

    def get_camera_streams(self, task_devices: List[str]) -> List[Any]:
        return [
            stream for stream_name, stream in self.streams.items()
            if DeviceManager.is_camera(stream_name) and stream_name in task_devices
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

    def start_cameras(self, filename: str, task_devices: List[str]) -> None:
        for stream in self.get_camera_streams(task_devices):
            try:
                stream.start(filename)
            except Exception as e:
                self.logger.exception(e)

    def stop_cameras(self, task_devices: List[str]):
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

    def iphone_frame_preview(self):
        for stream_name, stream in self.streams.items():
            if "IPhone" in stream_name:
                return stream.frame_preview()
        return None

    def close_streams(self) -> None:
        for stream_name, stream in self.streams.items():
            print(f"Closing stream {stream_name}")
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
                print(f"Re-streaming {stream_name} stream")
                self.logger.debug(f'Device Manager Reconnecting: {stream_name}')
                stream.start()
            print(f"-OUTLETID-:{stream_name}:{stream.outlet_id}")
