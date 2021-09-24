# -*- coding: utf-8 -*-
"""
Created on Wed May 12 16:13:50 2021

@author: CTR
"""

from ximea import xiapi
import threading
import uuid
from pylsl import StreamInfo, StreamOutlet
import cv2
import time


class VidRec_Ximea():
    def __init__(
            self,
            fourcc=cv2.VideoWriter_fourcc(
                *'MJPG'),
            sizex=round(
                1936 / 2),
        sizey=round(
                1216 / 2),
            fps=160,
            camSN="CACAU1723045"):
        # create instance for first connected camera
        cam = xiapi.Camera()
        # start communication
        # to open specific device, use:
        cam.open_device_by_SN(camSN)

        # settings
        cam.set_exposure(10000)
        cam.set_exposure(1000)
        # cam.set_param('width',968)
        # cam.set_param('height',608)
        self.open = True
        self.fourcc = fourcc
        self.fps = fps
        self.serial_num = camSN
        self.frameSize = (sizex, sizey)
        cam.set_param('width', sizex)
        cam.set_param('height', sizey)
        cam.set_gain(24)
        cam.set_gammaY(1)

        if fps is not None:
            cam.set_acq_timing_mode("XI_ACQ_TIMING_MODE_FRAME_RATE_LIMIT")
            cam.set_framerate(fps)
        else:
            cam.set_acq_timing_mode('XI_ACQ_TIMING_MODE_FREE_RUN')
        cam.set_imgdataformat('XI_RGB24')

        self.cam = cam

    def createOutlet(self, filename):
        streamName = 'XimeaFrameIndex'
        self.oulet_id = str(uuid.uuid4())
        info = StreamInfo(
            name=streamName,
            type='videostream',
            channel_format='int32',
            channel_count=2,
            source_id=self.oulet_id)
        info.desc().append_child_value("videoFile", filename)

        info.desc().append_child_value("size_rgb", str(self.frameSize))
        info.desc().append_child_value("serial_number", self.serial_num)
        info.desc().append_child_value("fps_rgb", str(self.fps))
        info.desc().append_child_value("device_model_id",
                                       self.cam.get_device_name().decode())
        print(f"-OUTLETID-:{streamName}:{self.oulet_id}")
        return StreamOutlet(info)

    def start(self, name="temp_video"):
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record)
        self.video_thread.start()

    def prepare(self, name="temp_video"):
        self.cam.start_acquisition()
        self.video_filename = "{}_ximea_{}.avi".format(name, time.time())
        self.video_out = cv2.VideoWriter(self.video_filename, self.fourcc,
                                         self.fps, self.frameSize)
        self.outlet = self.createOutlet(self.video_filename)
        self.streaming = True

    def record(self):
        self.recording = True
        self.frame_counter = 0
        img = xiapi.Image()
        print(f"Ximea recording {self.video_filename}")
        t0 = time.time()
        while self.recording:
            self.cam.get_image(img)
            tsmp = self.cam.get_timestamp()
            try:
                self.outlet.push_sample([self.frame_counter, tsmp])
            except BaseException:  # "OSError" from C++
                print(
                    f"Reopening brio {self.device_index} stream already closed")
                self.outlet = self.createOutlet(self.video_filename)
                self.outlet.push_sample([self.frame_counter])

            cvimg = img.get_image_data_numpy()

            # self.video_out.write(cvimg)
            self.frame_counter += 1

        print(
            f"Ximea recording ended with {self.frame_counter} frames in {time.time()-t0}")
        self.cam.stop_acquisition()
        self.recording = False
        self.video_out.release()

    def stop(self):
        if self.open and self.recording:
            self.recording = False
        self.streaming = False

    def close(self):
        self.stop()
        self.cam.close_device()
        self.open = False


if __name__ == "__main__":

    ximi = VidRec_Ximea()
    ximi.start()
    time.sleep(10)
    ximi.close()
    ximi.frameSize
