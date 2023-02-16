# -*- coding: utf-8 -*-
"""
Created on Mon Mar 29 10:46:13 2021

@author: adonay
"""
import os.path as op
from time import time
import multiprocessing as mp
import uuid
import functools
import warnings
from typing import NamedTuple, Tuple

import pyrealsense2 as rs
from pylsl import StreamInfo, StreamOutlet

warnings.filterwarnings("ignore")


def catch_exception(f):
    @functools.wraps(f)
    def func(*args, **kwargs):
        # try:
        return f(*args, **kwargs)
        # except Exception as e:
        # print('Caught an exception in function "{}" of type {}'.format(f.__name__, e))

    return func


class ConfigSettings(NamedTuple):
    """All the settings needed for an intel camera config object.
    Since the realsense objects can't be pickled, we pass this to the subprocess instead.
    """
    serial_num: str
    size_rgb: Tuple[int, int]
    fps_rgb: int
    size_depth: Tuple[int, int]
    fps_depth: int
    video_file_name: str


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

        self.open = True
        self.record_event = mp.Event()
        self.device_index = camindex[0]
        self.serial_num = camindex[1]
        self.fps = (fps_rgb, fps_depth)
        self.frameSize = (size_rgb, size_depth)
        self.device_id = device_id
        self.sensor_ids = sensor_ids

        self.outlet = self.createOutlet()

    @catch_exception
    def start(self, name="temp_video"):
        self.prepare(name)
        config_settings = ConfigSettings(
            serial_num=self.serial_num,
            size_rgb=self.frameSize[0],
            fps_rgb=self.fps[0],
            size_depth=self.frameSize[1],
            fps_depth=self.fps[1],
            video_file_name=self.video_filename,
        )
        
        self.record_event.set()
        self.video_process = mp.get_context('spawn').Process(
            target=VidRec_Intel.record,
            args=(
                self.record_event,
                config_settings,
                self.outlet,
            )
        )
        self.video_process.start()

    @catch_exception
    def prepare(self, name):
        self.name = name
        self.video_filename = "{}_intel{}.bag".format(name, self.device_index)
        print(f"-new_filename-:{self.streamName}:{op.split(self.video_filename)[-1]}")

    @catch_exception
    def createOutlet(self):
        self.streamName = f"IntelFrameIndex_cam{self.device_index}"
        self.outlet_id = str(uuid.uuid4())
        info = StreamInfo(
            name=self.streamName,
            type="videostream",
            channel_format="double64",
            channel_count=4,
            source_id=self.outlet_id,
        )

        info.desc().append_child_value("device_id", self.device_id)
        info.desc().append_child_value("sensor_ids", str(self.sensor_ids))
        info.desc().append_child_value("size_rgb", str(self.frameSize[0]))
        info.desc().append_child_value("size_depth", str(self.frameSize[1]))
        info.desc().append_child_value("serial_number", self.serial_num)
        info.desc().append_child_value("fps_rgb", str(self.fps[0]))
        info.desc().append_child_value("fps_depth", str(self.fps[1]))
        print(f"-OUTLETID-:{self.streamName}:{self.outlet_id}")
        return StreamOutlet(info)

    @staticmethod
    @catch_exception
    def config_realsense(settings: ConfigSettings) -> rs.config:
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

        config.enable_record_to_file(settings.video_file_name)
        return config

    @staticmethod
    @catch_exception
    def record(record_event: mp.Event, config_settings: ConfigSettings, outlet: StreamOutlet) -> None:
        """
        Record frames from an Intel RealSense camera until the recording event is cleared.
        All variables explicitly provided and not referenced through class object to prevent multiprocessing headaches.
        A separate process is used so that freezes do not cause other streams to stop and buffer.
        """
        frame_counter = 1
        pipeline = rs.pipeline()
        pipeline.start(VidRec_Intel.config_realsense(config_settings))

        # Avoid autoexposure frame drops
        dev = pipeline.get_active_profile().get_device()
        sens = dev.first_color_sensor()
        sens.set_option(rs.option.auto_exposure_priority, 0.0)

        while record_event.is_set():
            frame = pipeline.wait_for_frames(timeout_ms=1000)
            frame_num = frame.get_frame_number()
            timestamp = frame.get_timestamp()
            outlet.push_sample([frame_counter, frame_num, timestamp, time()])

            frame_counter += 1

        pipeline.stop()
        # print(f"Intel recording ended, total frames captured: {frame_num}, pushed lsl indexes: {frame_counter}")

    @catch_exception
    def stop(self, wait: bool = False):
        self.record_event.clear()
        if wait:
            self.video_process.join()

    @catch_exception
    def close(self):
        self.stop()
        self.config = []
