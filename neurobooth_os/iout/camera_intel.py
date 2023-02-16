# -*- coding: utf-8 -*-
"""
Created on Mon Mar 29 10:46:13 2021

@author: adonay
"""
import os.path as op
import sys
from time import time
import multiprocessing as mp
import uuid
import functools
import warnings
from typing import NamedTuple, Tuple, List, Optional

import pyrealsense2 as rs
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.netcomm import NewStdout

warnings.filterwarnings("ignore")


def catch_exception(f):
    @functools.wraps(f)
    def func(*args, **kwargs):
        # try:
        return f(*args, **kwargs)
        # except Exception as e:
        # print('Caught an exception in function "{}" of type {}'.format(f.__name__, e), flush=True)

    return func


class ConfigSettings(NamedTuple):
    """All the settings needed for an intel camera config object and LSL outlet.
    Since the realsense and LSL objects can't be pickled, we pass this to the subprocess instead.
    """
    serial_num: str
    size_rgb: Tuple[int, int]
    fps_rgb: int
    size_depth: Tuple[int, int]
    fps_depth: int
    device_index: int
    device_id: str
    sensor_ids: List[str]
    stream_name: str
    outlet_id: str


class VidRec_Intel:
    def __init__(
        self,
        size_rgb=(640, 480),
        size_depth=(640, 360),
        device_id="Intel_D455_1",
        sensor_ids=["Intel_D455_rgb_1", "Intel_D455_depth_1"],
        fps_rgb=60,
        fps_depth=60,
        camindex=[3, "SerialNumber"],
    ):
        device_index, serial_num = camindex
        self.config_settings = ConfigSettings(
            serial_num=serial_num,
            size_rgb=size_rgb,
            fps_rgb=fps_rgb,
            size_depth=size_depth,
            fps_depth=fps_depth,
            device_index=device_index,
            device_id=device_id,
            sensor_ids=sensor_ids,
            stream_name=f"IntelFrameIndex_cam{device_index}",
            outlet_id=str(uuid.uuid4()),
        )

        self.record_event = mp.Event()
        self.video_process: Optional[mp.Process] = None

        # Make the LSL outlet during startup just to be sure that it is registered by the GUI.
        # We will create another one in the subprocess since it cannot be pickled
        self.outlet = VidRec_Intel.create_outlet(self.config_settings)

    @catch_exception
    def start(self, name="temp_video"):
        self.video_process = mp.get_context('spawn').Process(
            target=VidRec_Intel.record,
            args=(
                self.record_event,
                self.config_settings,
                name,
                sys.stdout,
            )
        )
        self.record_event.set()
        self.video_process.start()

    @staticmethod
    @catch_exception
    def create_outlet(settings: ConfigSettings) -> StreamOutlet:
        info = StreamInfo(
            name=settings.stream_name,
            type="videostream",
            channel_format="double64",
            channel_count=4,
            source_id=settings.outlet_id,
        )

        info.desc().append_child_value("device_id", settings.device_id)
        info.desc().append_child_value("sensor_ids", str(settings.sensor_ids))
        info.desc().append_child_value("size_rgb", str(settings.size_rgb))
        info.desc().append_child_value("size_depth", str(settings.size_depth))
        info.desc().append_child_value("serial_number", settings.serial_num)
        info.desc().append_child_value("fps_rgb", str(settings.fps_rgb))
        info.desc().append_child_value("fps_depth", str(settings.size_depth))
        print(f"-OUTLETID-:{settings.stream_name}:{settings.outlet_id}", flush=True)
        return StreamOutlet(info)

    @staticmethod
    @catch_exception
    def config_realsense(settings: ConfigSettings, name: str) -> rs.config:
        config = rs.config()
        config.enable_device(settings.serial_num)

        config.enable_stream(
            rs.stream.color,
            settings.size_rgb[0],
            settings.size_rgb[1],
            rs.format.rgb8,
            settings.fps_rgb,
        )

        if settings.fps_depth:
            config.enable_stream(
                rs.stream.depth,
                settings.size_depth[0],
                settings.size_depth[1],
                rs.format.z16,
                settings.fps_depth,
            )

        video_filename = "{}_intel{}.bag".format(name, settings.device_index)
        config.enable_record_to_file(video_filename)
        print(f"-new_filename-:{settings.stream_name}:{op.split(video_filename)[-1]}", flush=True)

        return config

    @staticmethod
    @catch_exception
    def record(record_event: mp.Event, config_settings: ConfigSettings, name: str, stdout: NewStdout) -> None:
        """
        Record frames from an Intel RealSense camera until the recording event is cleared.
        All variables explicitly provided and not referenced through class object to prevent multiprocessing headaches.
        A separate process is used so that freezes do not cause other streams to stop and buffer.
        """
        sys.stdout = stdout

        outlet = VidRec_Intel.create_outlet(config_settings)

        pipeline = rs.pipeline()
        pipeline.start(VidRec_Intel.config_realsense(config_settings, name))

        # Avoid autoexposure frame drops
        dev = pipeline.get_active_profile().get_device()
        sens = dev.first_color_sensor()
        sens.set_option(rs.option.auto_exposure_priority, 0.0)

        frame_counter = 1
        while record_event.is_set():
            frame = pipeline.wait_for_frames(timeout_ms=1000)
            frame_num = frame.get_frame_number()
            timestamp = frame.get_timestamp()

            try:
                outlet.push_sample([frame_counter, frame_num, timestamp, time()])
            except BaseException:
                print("Reopening intel stream already closed", flush=True)
                outlet = VidRec_Intel.create_outlet(config_settings)
                outlet.push_sample([frame_counter, frame_num, timestamp, time()])

            frame_counter += 1

        pipeline.stop()
        # print(f"Intel recording ended, total frames captured: {frame_num}, pushed lsl indexes: {frame_counter}", flush=True)

    @catch_exception
    def stop(self, wait: bool = False):
        self.record_event.clear()
        if wait and self.video_process is not None:
            self.video_process.join()
            self.video_process = None

    @catch_exception
    def close(self):
        self.stop()
