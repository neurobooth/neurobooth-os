# -*- coding: utf-8 -*-
"""
Created on Wed May 12 16:13:50 2021

@author: CTR
"""
import os.path as op
import matplotlib.pyplot as plt
import numpy as np
import queue
import time
import os
import threading
import uuid

import cv2
import PySpin
from pylsl import StreamInfo, StreamOutlet
import skvideo
import skvideo.io
import h5py

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class VidRec_Flir:
    # def __init__(self,
    #              sizex=round(1936 / 2), sizey=round(1216 / 2), fps=196,
    #              camSN="20522874", exposure=4500, gain=20, gamma=.6,
    #              device_id="FLIR_blackfly_1", sensor_ids=['FLIR_rgb_1'], fd= .5):
    # Staging FLIR SN is 22348141
    def __init__(
        self,
        sizex=548,
        sizey=800,
        fps=195,
        offsetX=528,
        offsetY=152,
        camSN=os.getenv("FLIR_SN"),
        exposure=4500,
        gain=20,
        gamma=0.6,
        device_id="FLIR_blackfly_1",
        sensor_ids=["FLIR_rgb_1"],
        fd=1,
    ):
        # not currently using sizex, sizey --> need to update to use these parameters
        # need to read these parameters from database
        # need new column in database that allows parameters in json file
        self.open = False
        self.serial_num = camSN
        self.fps = fps
        self.serial_num = camSN
        self.exposure = exposure
        self.gain = gain
        self.gamma = gamma
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self.fd = fd
        self.sizex = sizex
        self.sizey = sizey
        self.offsetX = offsetX
        self.offsetY = offsetY
        self.recording = False
        self.get_cam()
        self.setup_cam()

        self.image_queue = queue.Queue(0)
        self.outlet = self.createOutlet()

    def get_cam(self):
        self.system = PySpin.System.GetInstance()
        cam_list = self.system.GetCameras()
        self.cam = cam_list.GetBySerial(self.serial_num)

    def try_setval(self, funct, val):
        try:
            funct(val)
        except:
            print(f"Flair {val} couldn't be changed")

    def setup_cam(self):
        self.cam.Init()
        self.open = True

        self.try_setval(
            self.cam.AcquisitionMode.SetValue, PySpin.AcquisitionMode_Continuous
        )
        self.try_setval(self.cam.ExposureAuto.SetValue, PySpin.ExposureAuto_Off)
        self.try_setval(self.cam.AcquisitionFrameRate.SetValue, self.fps)
        self.try_setval(self.cam.Height.SetValue, self.sizey)
        self.try_setval(self.cam.Width.SetValue, self.sizex)
        self.try_setval(self.cam.OffsetX.SetValue, self.offsetX)
        self.try_setval(self.cam.OffsetY.SetValue, self.offsetY)
        self.try_setval(self.cam.ExposureTime.SetValue, self.exposure)
        self.try_setval(self.cam.Gamma.SetValue, self.gamma)
        self.try_setval(self.cam.Gain.SetValue, self.gain)
        self.try_setval(
            self.cam.BalanceWhiteAuto.SetValue, PySpin.BalanceWhiteAuto_Once
        )

        s_node_map = self.cam.GetTLStreamNodeMap()
        handling_mode = PySpin.CEnumerationPtr(
            s_node_map.GetNode("StreamBufferHandlingMode")
        )
        handling_mode_entry = handling_mode.GetEntryByName("NewestOnly")
        handling_mode.SetIntValue(handling_mode_entry.GetValue())
        # cam.BalanceWhiteAuto.SetValue(0)

    def createOutlet(self):
        self.streamName = "FlirFrameIndex"
        self.oulet_id = str(uuid.uuid4())
        info = StreamInfo(
            name=self.streamName,
            type="videostream",
            channel_format="double64",
            channel_count=2,
            source_id=self.oulet_id,
        )

        info.desc().append_child_value("device_id", self.device_id)
        info.desc().append_child_value("sensor_ids", str(self.sensor_ids))
        # info.desc().append_child_value("size_rgb", str(self.frameSize))
        info.desc().append_child_value("serial_number", self.serial_num)
        info.desc().append_child_value("fps_rgb", str(self.fps))
        info.desc().append_child_value("exposure", str(self.exposure))
        info.desc().append_child_value("gain", str(self.gain))
        info.desc().append_child_value("gamma", str(self.gamma))

        # info.desc().append_child_value("device_model_id", self.cam.get_device_name().decode())
        print(f"-OUTLETID-:{self.streamName}:{self.oulet_id}")
        return StreamOutlet(info)

    # function to capture images, convert to numpy, send to queue, and release
    # from buffer in separate process
    def camCaptureVid(self):
        while self.recording or self.image_queue.qsize():
            try:
                dequeuedImage = self.image_queue.get(block=True, timeout=1)
                self.video_out.write(dequeuedImage)
            except queue.Empty:
                continue

    def start(self, name="temp_video"):
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record)
        self.video_thread.start()

    def imgage_proc(self):
        im = self.cam.GetNextImage(2000)
        tsmp = im.GetTimeStamp()
        imgarr = im.GetNDArray()
        im_conv = cv2.demosaicing(imgarr, cv2.COLOR_BayerBG2BGR)
        im.Release()
        return cv2.resize(im_conv, None, fx=self.fd, fy=self.fd), tsmp

    def prepare(self, name="temp_video"):
        self.cam.BeginAcquisition()
        im, _ = self.imgage_proc()
        self.frameSize = (im.shape[1], im.shape[0])
        self.video_filename = "{}_flir.avi".format(name)

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.FRAME_RATE_OUT = self.cam.AcquisitionResultingFrameRate()
        self.video_out = cv2.VideoWriter(
            self.video_filename, fourcc, self.FRAME_RATE_OUT, self.frameSize
        )
        print(f"-new_filename-:{self.streamName}:{op.split(self.video_filename)[-1]}")

        self.streaming = True

    def record(self):
        self.recording = True
        self.frame_counter = 0
        self.save_thread = threading.Thread(target=self.camCaptureVid)
        self.save_thread.start()

        self.stamp = []
        while self.recording:
            # Exception for failed waiting self.cam.GetNextImage(1000)
            try:
                im, tsmp = self.imgage_proc()
            except:
                continue

            self.image_queue.put(im)
            self.stamp.append(tsmp)

            try:
                self.outlet.push_sample([self.frame_counter, tsmp])
            except BaseException:
                print(f"Reopening FLIR {self.device_index} stream already closed")
                self.outlet = self.createOutlet(self.video_filename)
                self.outlet.push_sample([self.frame_counter, tsmp])

            # self.video_out.write(im_conv_d)
            self.frame_counter += 1

            if not self.frame_counter % 1000 and self.image_queue.qsize() > 2:
                print(
                    f"Queue length is {self.image_queue.qsize()} frame count: {self.frame_counter}"
                )

        # print(f"FLIR recording ended with {self.frame_counter} frames in {time.time()-t0}")
        self.cam.EndAcquisition()
        self.recording = False
        self.save_thread.join()
        self.video_out.release()
        # print(f"FLIR video saving ended in {time.time()-t0} sec")

    def stop(self):
        if self.open and self.recording:
            self.recording = False
            self.video_thread.join()

        self.streaming = False

    def close(self):
        self.stop()
        self.cam.DeInit()
        self.open = False


if __name__ == "__main__":

    flir = VidRec_Flir()
    flir.start()
    time.sleep(10)
    flir.close()
    flir.close()
    tdiff = np.diff(flir.stamp) / 1e6
    plt.figure(), plt.hist(tdiff, 50), plt.show()
    plt.figure(), plt.plot(tdiff), plt.show()
    print("diff max min", tdiff.max() - tdiff.min())
