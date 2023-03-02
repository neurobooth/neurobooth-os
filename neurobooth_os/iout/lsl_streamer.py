# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""
import time
import logging
from typing import Dict, List, Any
from abc import abstractmethod, ABC

from neurobooth_os import config
from neurobooth_os.iout import metadator as meta

from mbientlab.warble import BleScanner
from time import sleep


def setup_log(name, node_name: str = None):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not node_name:
        log_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        #filename = f"./{name}.log"
        #log_handler = logging.FileHandler(filename)
        #log_handler.setLevel(logging.DEBUG)
        #log_handler.setFormatter(log_format)
        #logger.addHandler(log_handler)
    return logger


logger = setup_log(__name__)


class DeviceStreamManager(ABC):
    """
    Create and manage device LSL streams.

    Life cycle:
    1. preprare: Creates the streams. Some streams will start streaming upon creation.
    2. record_start: Begin streaming data on devices that were not started upon creation.
    3. record_stop: Stop streaming data on devices that were not started upon creation.
    4. close: Stop streaming and close all streams.
    """

    # ================================================================================
    # Class Initialization
    # ================================================================================

    streams: Dict[str, Any]
    task_dev_kw: Dict[str, str]

    def __init__(self):
        self.streams = {}
        self.task_devs_kw = None

    # ================================================================================
    # Utility Functions
    # Exposes streams to server scripts.
    # ================================================================================

    def get_streams_by_name(self, name: str) -> List[Any]:
        return [stream for stream_name, stream in self.streams.items() if (name in stream_name)]

    def has_stream(self, name: str) -> bool:
        return name in self.streams

    # ================================================================================
    # Prepare-related Functions
    # ================================================================================

    def prepare(self, collection_id: str, conn: Any) -> None:
        self.task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)

        if len(self.streams):
            print("Checking prepared devices")
            self.reconnect_streams()
        else:
            # This will also start the mouse and mBients
            self.start_lsl_threads(collection_id, conn=conn)

    def start_lsl_threads(self, collection_id: str = 'mvp_030', win: Any = None, conn: Any = None) -> None:
        """
        Initiate devices and LSL streams based on databased parameters.

        Parameters
        ----------
        collection_id : str, optional
            Name of studies collection in the database, by default "mvp_025"
        win : object, optional
            Pycharm window, by default None
        conn : object, optional
            Connector to the database, by default None
        """

        if conn is None:
            print("getting conn")
            conn = meta.get_conn()

        # Get params from all tasks
        kwarg_devs = meta._get_device_kwargs_by_task(collection_id, conn)
        # Get all device params from session
        kwarg_alldevs = {}
        for dc in kwarg_devs.values():
            kwarg_alldevs.update(dc)

        scann_BLE()

        self.streams = {}
        self._start_lsl_threads_server(win=win, kwarg_alldevs=kwarg_alldevs)

    @abstractmethod
    def _start_lsl_threads_server(self, win: Any, kwarg_alldevs: Dict[str, Any]) -> None:
        """Handle server-specific implementation details of start_lsl_threads"""
        raise NotImplementedError()

    def reconnect_streams(self) -> None:
        for name, stream in self.streams.items():
            if name.split("_")[0] in ["hiFeed", "Intel", "FLIR", "IPhone"]:
                continue

            if not stream.streaming:
                print(f"Re-streaming {name} stream")
                stream.start()
            print(f"-OUTLETID-:{name}:{stream.oulet_id}")

    # ================================================================================
    # Remaining Lifecycle Functions
    # Some record_start and record_stop functions are implemented by subclasses.
    # ================================================================================

    def record_start_mbients(self) -> None:
        for name, stream in self.streams.items():
            if "Mbient" in name:
                try:
                    if not stream.device.is_connected:
                        stream.try_reconnect()
                except Exception as e:
                    print(e)
                    pass

    def record_stop_mbients(self) -> None:
        for name, stream in self.streams.items():
            if "Mbient" in name:
                stream.lsl_push = False

    def close(self) -> None:
        for name, stream in self.streams.items():
            print(f"Closing {name} stream")
            if name.split("_")[0] in ["hiFeed", "Intel", "FLIR", "IPhone"]:
                stream.close()
            else:
                stream.stop()


class DeviceStreamManagerACQ(DeviceStreamManager):
    def __init__(self):
        super().__init__()

    def _start_lsl_threads_server(self, win: Any, kwarg_alldevs: Dict[str, Any]) -> None:
        from neurobooth_os.iout.microphone import MicStream
        from neurobooth_os.iout.camera_intel import VidRec_Intel
        from neurobooth_os.iout.flir_cam import VidRec_Flir
        from neurobooth_os.iout.iphone import IPhone

        for kdev, argsdev in kwarg_alldevs.items():
            if "Intel" in kdev:
                self.streams[kdev] = VidRec_Intel(**argsdev)
            elif "Mbient" in kdev:
                # Don't connect mbients from STM
                if any([d in kdev for d in ["Mbient_LF", "Mbient_RF"]]):
                    continue
                self.streams[kdev] = connect_mbient(**argsdev)
                if self.streams[kdev] is None:
                    del self.streams[kdev]
                else:
                    self.streams[kdev].start()
            elif "FLIR" in kdev:
                try:
                    self.streams[kdev] = VidRec_Flir(**argsdev)
                except:
                    logger.error(f"FLIR not connected")
            elif "Mic_Yeti" in kdev:
                self.streams[kdev] = MicStream(**argsdev)
                self.streams[kdev].start()
            elif "IPhone" in kdev:
                self.streams[kdev] = IPhone(name="IPhoneFrameIndex", **argsdev)
                success = self.streams[kdev].prepare()
                if not success and self.streams.get(kdev) is not None:
                    del self.streams[kdev]

    def record_start_cameras(self, file_name: str, task: str) -> None:
        for name, stream in self.streams.items():
            if name.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]:
                if self.task_devs_kw[task].get(name):
                    try:
                        stream.start(file_name)
                    except:
                        continue

    def record_stop_cameras(self, task: str) -> None:
        for name, stream in self.streams.items():
            if name.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]:
                if self.task_devs_kw[task].get(name):
                    stream.stop()


class DeviceStreamManagerSTM(DeviceStreamManager):
    def __init__(self):
        super().__init__()

    def _start_lsl_threads_server(self, win: Any, kwarg_alldevs: Dict[str, Any]) -> None:
        from neurobooth_os.iout import marker_stream
        from neurobooth_os.iout.mouse_tracker import MouseStream
        from neurobooth_os.iout.eyelink_tracker import EyeTracker

        self.streams["marker"] = marker_stream()

        for kdev, argsdev in kwarg_alldevs.items():
            if "Eyelink" in kdev:
                self.streams["Eyelink"] = EyeTracker(win=win, **argsdev)
            elif "Mouse" in kdev:
                self.streams["mouse"] = MouseStream(**argsdev)
                self.streams["mouse"].start()

            elif any([d in kdev for d in ["Mbient_LF", "Mbient_RF"]]):
                self.streams[kdev] = connect_mbient(**argsdev)
                if self.streams[kdev] is None:
                    del self.streams[kdev]
                else:
                    self.streams[kdev].start()

    def should_run_eyelink(self, task: str) -> bool:
        return (
            ('Eyelink' in self.streams)
            and (any('Eyelink' in d for d in list(self.task_devs_kw[task])))
            and ('calibration_task' not in task)
        )

    def record_start_eyelink(self, task: str, file_name: str) -> None:
        if self.should_run_eyelink(task):
            self.streams['Eyelink'].start(file_name)

    def record_stop_eyelink(self, task: str) -> None:
        if self.should_run_eyelink(task):
            self.streams['Eyelink'].stop()


class DeviceStreamManagerMockACQ(DeviceStreamManagerACQ):
    """Overwrites _start_lsl_threads_server to be usable with a mock setup"""

    def _start_lsl_threads_server(self, win: Any, kwarg_alldevs: Dict[str, Any]) -> None:
        from neurobooth_os.mock import mock_device_streamer as mock_dev
        from neurobooth_os.iout.iphone import IPhone

        for kdev, argsdev in kwarg_alldevs.items():
            if "Intel" in kdev:
                self.streams[kdev] = mock_dev.MockCamera(**argsdev)
            elif "Mbient" in kdev:
                self.streams[kdev] = mock_dev.MockMbient(**argsdev)
                self.streams[kdev].start()
            elif "IPhone" in kdev:
                self.streams[kdev] = IPhone(name="IPhoneFrameIndex", **argsdev)
                success = self.streams[kdev].prepare()
                if not success and self.streams.get(kdev) is not None:
                    del self.streams[kdev]


class DeviceStreamManagerMockSTM(DeviceStreamManagerSTM):
    """Overwrites _start_lsl_threads_server to be usable with a mock setup"""

    def _start_lsl_threads_server(self, win: Any, kwarg_alldevs: Dict[str, Any]) -> None:
        from neurobooth_os.iout import marker_stream
        self.streams["marker"] = marker_stream()


# ================================================================================
# Utility functions for handling BLE and Mbients
# ================================================================================


def scann_BLE(sleep_period=10):
    print("scanning for devices...")
    devices = {}

    def handler(result):
        devices[result.mac] = result.name

    BleScanner.set_handler(handler)
    BleScanner.start()

    sleep(sleep_period)
    BleScanner.stop()


def connect_mbient(dev_name="LH", mac="CE:F3:BD:BD:04:8F", try_nmax=5, **kwarg):
    from neurobooth_os.iout.mbient import Sensor, reset_mbient

    tinx = 0
    print(f"Trying to connect mbient {dev_name}, mac {mac}")
    while True:
        try:
            sens = Sensor(mac, dev_name, **kwarg)
            return sens
        except Exception as e:
            print(
                f"Trying to connect mbient {dev_name}, {tinx} out of {try_nmax} tries {e}"
            )
            tinx += 1
            if tinx >= try_nmax:
                try:
                    reset_mbient(mac, dev_name)
                    sens = Sensor(mac, dev_name, **kwarg)
                    return sens
                except:
                    print(f"Failed to connect mbient {dev_name}")
                break
            time.sleep(1)
