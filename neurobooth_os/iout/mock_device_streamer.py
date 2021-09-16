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

from pylsl import StreamInfo, StreamOutlet


class MockLSLDevice(object):
    """Mock Device that Streams LSL samples.

    Parameters
    ----------
    nchans : int
        Number of channels.
    frames_buffer : int | None
        If not None, data is sent in chunks. Default None
    ch_type : type
        data type of lsl stream
    name : str
        Name of the LSL outlet stream.
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

    def __init__(self, nchans=3, frames_buffer=None, data_type="float32",
                 name="mock", stream_type='Experimental', srate=100,
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

        self.streaming = False
        self.createOutlet()

    def createOutlet(self):

        if self.oulet_id == '':
            self.oulet_id = str(uuid.uuid4())

        info = StreamInfo(name=self.name,
                          type=self.stream_type,
                          channel_count = self.nchans,
                          nominal_srate = self.srate,
                          channel_format = self.data_type,
                          source_id = self.oulet_id)

        # info.desc().append_child_value("filename", filename)
        info.desc().append_child_value("device_id", self.device_id)
        info.desc().append_child_value("sensor_ids", str(self.sensor_ids))
        info.desc().append_child_value("fps", str(self.srate))

        self.outlet = StreamOutlet(info, chunk_size=0, max_buffered=10)
        print(f"-OUTLETID-:{self.name}:{self.oulet_id}")


    def start(self):
        """Start mock LSL stream."""

        self.stream_thread = threading.Thread(target=self.stream, daemon=True)
        # self.process = Process(target=self._initiate_stream, daemon=True)
        self.stream_thread.start()
        return

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


if __name__ == "__main__":

    dev = MockLSLDevice(nchans=10, srate=100, data_type="float32")
    # dev.start()
    # time.sleep(10)
    # dev.stop()
    with dev:
        time.sleep(10)

