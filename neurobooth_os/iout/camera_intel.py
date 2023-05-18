# -*- coding: utf-8 -*-
"""
Created on Mon Mar 29 10:46:13 2021

@author: adonay
"""
import os.path as op
from time import sleep as tsleep
from time import time
import threading
import uuid
import functools
import warnings
import logging

from pylsl import local_clock
import pyrealsense2 as rs
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description

warnings.filterwarnings("ignore")


def catch_exception(f):
    @functools.wraps(f)
    def func(*args, **kwargs):
        # try:
        return f(*args, **kwargs)
        # except Exception as e:
        # print('Caught an exception in function "{}" of type {}'.format(f.__name__, e))

    return func


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
        self.recording = False
        self.device_index = camindex[0]
        self.serial_num = camindex[1]
        self.fps = (fps_rgb, fps_depth)
        self.frameSize = (size_rgb, size_depth)
        self.device_id = device_id
        self.sensor_ids = sensor_ids

        self.config = rs.config()
        self.config.enable_device(self.serial_num)
        self.pipeline = rs.pipeline()

        self.config.enable_stream(
            rs.stream.color,
            self.frameSize[0][0],
            self.frameSize[0][1],
            rs.format.rgb8,
            self.fps[0],
        )

        if fps_depth:
            self.config.enable_stream(
                rs.stream.depth,
                self.frameSize[1][0],
                self.frameSize[1][1],
                rs.format.z16,
                self.fps[1],
            )

        self.outlet = self.createOutlet()

        self.logger = logging.getLogger('session')
        self.logger.debug(f'RealSense: fps={str(self.fps)}; frame_size={str(self.frameSize)}')

    @catch_exception
    def start(self, name="temp_video"):
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record)
        self.logger.debug(f'RealSense: Beginning recording for {self.device_index} ({self.serial_num})')
        self.video_thread.start()

    @catch_exception
    def prepare(self, name):
        self.name = name
        self.video_filename = "{}_intel{}.bag".format(name, self.device_index)
        self.config.enable_record_to_file(self.video_filename)
        print(f"-new_filename-:{self.streamName}:{op.split(self.video_filename)[-1]}")

    @catch_exception
    def createOutlet(self):
        self.streamName = f"IntelFrameIndex_cam{self.device_index}"
        self.outlet_id = str(uuid.uuid4())
        info = set_stream_description(
            stream_info=StreamInfo(
                name=self.streamName,
                type="videostream",
                channel_format="double64",
                channel_count=4,
                source_id=self.outlet_id,
            ),
            device_id=self.device_id,
            sensor_ids=self.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['FrameNum', 'FrameNum_RealSense', 'Time_RealSense', 'Time_ACQ'],
            column_desc={
                'FrameNum': 'Locally-tracked frame number',
                'FrameNum_RealSense': 'Camera-tracked frame number',
                'Time_RealSense': 'Camera timestamp (ms)',
                'Time_ACQ': 'Local machine timestamp (s)',
            },
            serial_number=self.serial_num,
            size_rgb=str(self.frameSize[0]),
            size_depth=str(self.frameSize[1]),
            fps_rgb=str(self.fps[0]),
            fps_depth=str(self.fps[1]),
        )
        print(f"-OUTLETID-:{self.streamName}:{self.outlet_id}")
        return StreamOutlet(info)

    @catch_exception
    def record(self):
        self.recording = True
        self.frame_counter = 1
        self.pipeline.start(self.config)

        # Avoid autoexposure frame drops
        dev = self.pipeline.get_active_profile().get_device()
        sens = dev.first_color_sensor()
        sens.set_option(rs.option.auto_exposure_priority, 0.0)

        self.toffset = time() - local_clock()

        while self.recording:
            frame = self.pipeline.wait_for_frames(timeout_ms=1000)
            # frame = self.pipeline.poll_for_frames()
            # if not frame:
            #     continue
            # else:
            #     print(f" frame {self.frame_counter} in intel {self.device_index}")
            self.n = frame.get_frame_number()
            # self.ftsmp = frame.get_timestamp()
            # self.tsmp = (self.ftsmp - self.toffset)*1e-3
            self.tsmp = frame.get_timestamp()
            try:
                # self.outlet.push_sample([self.frame_counter, self.n], timestamp= self.tsmp)
                self.outlet.push_sample([self.frame_counter, self.n, self.tsmp, time()])
            except BaseException:
                print("Reopening intel stream already closed")
                self.outlet = self.createOutlet(self.name)
                self.outlet.push_sample([self.frame_counter, self.n, self.tsmp, time()])

            self.frame_counter += 1
            # countdown(1/(4*self.fps[0]))

        self.logger.debug(f'RealSense: {self.device_index} ({self.serial_num}) exited record loop.')
        self.pipeline.stop()
        self.logger.debug(f'RealSense: {self.device_index} ({self.serial_num}) stopped pipeline.')
        # print(f"Intel {self.device_index} recording ended, total frames captured: {self.n}, pushed lsl indexes: {self.frame_counter}")

    @catch_exception
    def stop(self):
        self.logger.debug(f'RealSense: Setting record stop flag for {self.device_index} ({self.serial_num})')
        if self.recording:
            self.recording = False

    @catch_exception
    def close(self):
        self.previewing = False
        self.stop()
        self.config = []


def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()
