#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep 16 12:58:47 2021

@author: adonay
"""

import threading
import uuid
import numpy as np
import time
import pylsl
from pylsl import StreamInfo, StreamOutlet
import numpy as np

class MockLSLDevice(object):
    """Mock Device that Streams LSL samples.

    Parameters
    ----------
    name : str
        Name of the LSL outlet stream.
    nchans : int
        Number of channels.
    frames_buffer : int | None
        If not None, data is sent in chunks. Default None
    stream_outlet : bool
        If true the outlet will be streamed and outlet id will be printed.
    ch_type : type
        data type of lsl stream
    stream_type : str
        Type of LSL stream, eg. Experimental
    srate : int
        sampling rate of the LSL stream
    source_id : str
        Str that identifies the LSL stream
    device_id : str
        Name of the device
    sensor_ids : List
        Name of the sensors in the device
    """

    def __init__(self, name="mock", nchans=3, frames_buffer=None, stream_outlet=True,
                 data_type="float32", stream_type='Experimental', srate=100,
                 source_id='', device_id="mock_dev_1", sensor_ids=['mock_sens_1']):

        self.nchans = nchans
        self.frames_buffer = frames_buffer
        self.data_type = data_type
        self.name = name
        self.stream_type = stream_type
        self.srate = srate
        self.oulet_id = source_id
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self.stream_outlet = stream_outlet

        self.streaming = False
        self.frame_counter = 0
        self.create_outlet()

    def create_outlet(self):

        if self.oulet_id == '':
            self.oulet_id = str(uuid.uuid4())

        self.info = StreamInfo(name=self.name,
                              type=self.stream_type,
                              channel_count=self.nchans,
                              nominal_srate=self.srate,
                              channel_format=self.data_type,
                              source_id=self.oulet_id)

        # info.desc().append_child_value("filename", filename)
        self.info.desc().append_child_value("device_id", self.device_id)
        self.info.desc().append_child_value("sensor_ids", str(self.sensor_ids))
        self.info.desc().append_child_value("fps", str(self.srate))
        if self.stream_outlet:
            self.stream_outlet_info()

    def stream_outlet_info(self):
        self.outlet = StreamOutlet(self.info, chunk_size=0, max_buffered=10)
        print(f"-OUTLETID-:{self.name}:{self.oulet_id}")

    def start(self):
        """Start mock LSL stream."""

        self.stream_thread = threading.Thread(target=self.stream, daemon=True)
        # self.process = Process(target=self._initiate_stream, daemon=True)
        self.stream_thread.start()

    def stop(self):
        """Stop mock LSL stream."""
        if self.streaming:
            self.streaming = False
            self.stream_thread.join()
            # self.process.terminate()

    def __enter__(self):
        """Enter the context manager."""
        self.start()
        return self

    def __exit__(self, type_, value, traceback):
        """Exit the context manager."""
        self.stop()

    def stream(self):
        """ Generate data and push smples into outlet stream"""
        self.streaming = True
        print("Streaming data")
        self.frame_counter = 0
        stime, t0 = time.time(), time.time()
        while self.streaming:
            data = np.empty(self.nchans, dtype=self.data_type)
            self.outlet.push_sample(data)
            self.frame_counter += 1
            stime += 1/self.srate
            tsleep = stime - time.time()
            if tsleep > 0:
                time.sleep(tsleep)

        print(f"Mock stream closed with {self.frame_counter} pushed samples",
              f" in {time.time() - t0 :.3} secs")


class MockMbient(MockLSLDevice):
    """Mock Mbient Device that Streams LSL samples with Mbient child info.

    Parameters
    ----------
    name : str
        Name of the LSL outlet stream.
    nchans : int
        Number of channels.
    frames_buffer : int | None
        If not None, data is sent in chunks. Default None
    stream_outlet : bool
        If true the outlet will be streamed and outlet id will be printed.
    ch_type : type
        data type of lsl stream
    stream_type : str
        Type of LSL stream, eg. Experimental
    srate : int
        sampling rate of the LSL stream
    source_id : str
        Str that identifies the LSL stream
    device_id : str
        Name of the device
    sensor_ids : List
        Name of the sensors in the device
    """
    def __init__(self, name="Mbient", nchans=7, frames_buffer=None,
                 data_type="float32", stream_type='Experimental', srate=100,
                 source_id='', device_id="mock_dev_1",  stream_outlet=False,
                 sensor_ids=['mock_mbient_acc_1', 'mock_mbient_grad_1']):

        super().__init__(name, nchans, frames_buffer, stream_outlet,
                         data_type, stream_type, srate,
                         source_id, device_id, sensor_ids)

        col_names = ["time_stamp", "acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z"]
        self.info.desc().append_child_value("col_names", str(col_names))
        self.info.desc().append_child_value("device_id", device_id)
        self.info.desc().append_child_value("sensor_ids", str(sensor_ids))

        self.stream_outlet_info()



class MockCamera(MockLSLDevice):
    """Mock Camera Recording Device that Streams LSL frame index and timestamp.

    Parameters
    ----------
    name : str
        Name of the LSL outlet stream.
    nchans : int
        Number of channels.
    frames_buffer : int | None
        If not None, data is sent in chunks. Default None
    stream_outlet : bool
        If true the outlet will be streamed and outlet id will be printed.
    ch_type : type
        data type of lsl stream
    stream_type : str
        Type of LSL stream, eg. Experimental
    srate : int
        sampling rate of the LSL stream
    sizex : int
        Height of the frame.
    sizey : int
        With of the frame.
    source_id : str
        Str that identifies the LSL stream
    device_id : str
        Name of the device
    sensor_ids : List
        Name of the sensors in the device
    """
    def __init__(self, name="Intel", nchans=2, frames_buffer=None,
                 data_type="float32", stream_type='Experimental', srate=180,
                 sizex=1080, sizey=720,
                 source_id='', device_id="Intel_dev_1", stream_outlet=False,
                 sensor_ids=['mock_Intel_rgb_1', 'mock_Intel_depth_1']):

        super().__init__(name, nchans, frames_buffer, stream_outlet,
                         data_type, stream_type, srate,
                         source_id, device_id, sensor_ids)

        self.sizex = sizex
        self.sizey = sizey
        self.recording = False

    def prepare(self, name="temp_video"):
        """ Creates stream with child info and sets video filename."""
        self.video_filename = "{}_flir_{}.bag".format(name, time.time())
        self.info.desc().append_child_value("filename", self.video_filename)
        self.stream_outlet_info()

    def start(self, name="temp_video"):
        """Start camera mock LSL stream."""
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record, daemon=True)
        self.video_thread.start()

    def record(self):
        """ Generate frame data and push frame index into outlet stream."""
        self.recording = True
        self.frame_counter = 0
        print(f"{self.name} recording {self.video_filename}")

        stime, t0 = time.time(), time.time()
        while self.recording:
            frame = np.empty((self.sizex, self.sizey), dtype=np.uint8)
            tsmp = pylsl.local_clock()

            try:
                self.outlet.push_sample([self.frame_counter, tsmp])
            except:  # "OSError" from C++
                print(f"Reopening {self.name} stream already closed")
                self.stream_outlet_info()
                self.outlet.push_sample([self.frame_counter, tsmp])

            self.frame_counter += 1
            stime += 1/self.srate
            tsleep = stime - time.time()
            if tsleep > 0:
                time.sleep(tsleep)

        print(f"{self.name} recording ended in {time.time() - t0 :.3} secs"
              f", total frames captured: {self.frame_counter}")

    def stop(self):
        """Stop mock LSL stream."""
        if self.recording:
            self.recording = False
            self.video_thread.join()



if __name__ == "__main__":

    from neurobooth_os.iout.marker import marker_stream

    dev_stream = MockLSLDevice(name="mock", nchans=5)
    with dev_stream:
        time.sleep(10)
    mbient = MockMbient()
    cam = MockCamera()
    marker = marker_stream()

    cam.start()
    dev_stream.start()
    mbient.start()

    marker.push_sample([f"Stream-mark"])

    cam.stop()
    dev_stream.stop()
    mbient.stop()
