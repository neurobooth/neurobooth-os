# -*- coding: utf-8 -*-
"""
Created on Mon Mar 29 10:46:13 2021

@author: adonay
"""
import os.path as op
from time import time
import threading
import uuid
import warnings
import logging

from pylsl import local_clock
import pyrealsense2 as rs
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME

warnings.filterwarnings("ignore")


class RealSenseException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class VidRec_Intel:
    def __init__(
        self,
        device_args: DeviceArgs,
        camindex=[3, "SerialNumber"],
    ):

        self.open = True
        self.recording = threading.Event()
        self.record_stopped_flag = threading.Event()
        self.recording.clear()
        self.video_thread = None

        self.device_index = camindex[0]
        self.serial_num = camindex[1]
        self.fps = device_args.fps()
        self.frameSize = device_args.framesize()
        self.device_id = device_args.device_id
        self.sensor_ids = device_args.sensor_ids
        self.config = rs.config()
        self.config.enable_device(self.serial_num)
        self.pipeline = rs.pipeline()

        print(f"Framesize: {self.frameSize}")
        print(f"Framesize: {self.frameSize[0][0]}")
        print(f"Framesize: {self.frameSize[0][1]}")

        print(f"FPS: {self.fps}")
        print(f"FPS: {self.fps[0]}")
        print(f"RS: {rs.stream.color}")
        print(f"RS: {rs.format.rgb8}")
        self.config.enable_stream(
            rs.stream.color,
            self.frameSize[0][0],
            self.frameSize[0][1],
            rs.format.rgb8,
            self.fps[0],
        )

        if device_args.has_depth_sensor():
            self.config.enable_stream(
                rs.stream.depth,
                self.frameSize[1][0],
                self.frameSize[1][1],
                rs.format.z16,
                self.fps[1],
            )

        self.outlet = self.createOutlet()

        self.logger = logging.getLogger(APP_LOG_NAME)
        self.logger.debug(
            f'RealSense [{self.device_index}] ({self.serial_num}): fps={str(self.fps)}; frame_size={str(self.frameSize)}'
        )

    def start(self, name="temp_video"):
        if self.video_thread is not None and self.video_thread.is_alive():
            error_msg = f'RealSense [{self.device_index}]: Attempting to start new recording thread while old one is still alive!'
            self.logger.error(error_msg)
            raise RealSenseException(error_msg)

        self.prepare(name)
        self.recording.set()
        self.record_stopped_flag.clear()
        self.video_thread = threading.Thread(target=self.record)
        self.logger.debug(f'RealSense [{self.device_index}]: Beginning Recording')
        self.video_thread.start()

    def prepare(self, name):
        self.name = name
        self.video_filename = "{}_intel{}.bag".format(name, self.device_index)
        self.config.enable_record_to_file(self.video_filename)
        print(f"-new_filename-:{self.streamName}:{op.split(self.video_filename)[-1]}")

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

    def record(self):
        self.frame_counter = 1
        
        try:
            self.logger.debug(f'RealSense [{self.device_index}]: Starting Pipeline')
            self.pipeline.start(self.config)
        except Exception as e:
            self.logger.error(f'RealSense [{self.device_index}]: Unable to start pipeline: {e}')
            self.record_stopped_flag.set()
            return

        # Avoid autoexposure frame drops
        dev = self.pipeline.get_active_profile().get_device()
        sens = dev.first_color_sensor()
        sens.set_option(rs.option.auto_exposure_priority, 0.0)

        self.toffset = time() - local_clock()

        self.logger.debug(f'RealSense [{self.device_index}]: Entering LSL Loop')
        while self.recording.is_set():
            success, frame = self.pipeline.try_wait_for_frames(timeout_ms=1000)
            if not success:
                self.logger.warning(f'RealSense [{self.device_index}]: Timeout when waiting for frame!')
                continue

            self.n = frame.get_frame_number()
            self.tsmp = frame.get_timestamp()
            try:
                self.outlet.push_sample([self.frame_counter, self.n, self.tsmp, time()])
            except Exception as e:
                self.logger.warning(f'RealSense [{self.device_index}]: Reopening closed stream: {e}')
                self.outlet = self.createOutlet()
                self.outlet.push_sample([self.frame_counter, self.n, self.tsmp, time()])

            self.frame_counter += 1

        self.logger.debug(f'RealSense [{self.device_index}]: Exited Record Loop')
        self.pipeline.stop()
        self.record_stopped_flag.set()
        self.logger.debug(f'RealSense [{self.device_index}]: Stopped Pipeline')

    def stop(self):
        self.logger.debug(f'RealSense [{self.device_index}]: Setting Record Stop Flag')
        self.recording.clear()

    def close(self):
        self.previewing = False
        self.stop()
        self.config = []

    def ensure_stopped(self, timeout_seconds: float) -> None:
        """Check to make sure the recording is actually stopped."""
        if not self.record_stopped_flag.wait(timeout=timeout_seconds):
            self.logger.error(f'RealSense [{self.device_index}]: Potential Zombie Detected!')
            try:
                self.pipeline.stop()
            except Exception as e:
                self.logger.error(f'RealSense [{self.device_index}]: Unable to stop pipeline: {e}')
