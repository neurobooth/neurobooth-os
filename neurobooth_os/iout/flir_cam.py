# -*- coding: utf-8 -*-
"""
Created on Wed May 12 16:13:50 2021

@author: CTR
"""

import PySpin
import matplotlib.pyplot as plt
import numpy as np
import queue
import time
import os
import cv2
import threading
import uuid
from pylsl import StreamInfo, StreamOutlet
import skvideo
import skvideo.io


class VidRec_Flir():        
    def __init__(self, fourcc=cv2.VideoWriter_fourcc(*'MJPG'),
                 sizex=round(1936/2), sizey=round(1216/2), fps=160, 
                 camSN="20522874", exposure=4500, gain=20, gamma=.6):
        
        self.open = False
        self.serial_num = camSN 
        self.fourcc = fourcc
        self.fps = fps 
        self.serial_num = camSN
        self.exposure = exposure
        self.gain = gain
        self.gamma = gamma
        
        self.get_cam()
        self.setup_cam()
        
        self.image_queue = queue.Queue()
        
        
        
    def get_cam(self):
        self.system = PySpin.System.GetInstance()
        cam_list = self.system.GetCameras()
        self.cam = cam_list.GetBySerial(self.serial_num)        
        
        
    def setup_cam(self):        
        self.cam.Init()
        self.open = True
        self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)        
        self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
                
        self.cam.ExposureTime.SetValue(self.exposure)
        self.cam.Gamma.SetValue(self.gamma)
        self.cam.Gain.SetValue(self.gain)
        self.cam.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Once)
        # cam.BalanceWhiteAuto.SetValue(0)


    def createOutlet(self, filename):
        streamName = 'FlirFrameIndex'
        self.oulet_id = str(uuid.uuid4())
        info = StreamInfo(name=streamName, type='videostream', channel_format='int32', channel_count=2,
                          source_id=self.oulet_id)
        
        info.desc().append_child_value("videoFile", filename)
 
        info.desc().append_child_value("size_rgb", str(self.frameSize)) 
        info.desc().append_child_value("serial_number", self.serial_num) 
        info.desc().append_child_value("fps_rgb", str(self.fps))
        # info.desc().append_child_value("device_model_id", self.cam.get_device_name().decode())
        print(f"-OUTLETID-:{streamName}:{self.oulet_id}")
        return StreamOutlet(info)

             
    def camCaptureVid(self): #function to capture images, convert to numpy, send to queue, and release from buffer in separate process
        while self.recording or self.image_queue.qsize():
            camNotReady = self.image_queue.empty() # wait for  images readys
            while camNotReady: #wait until ready in a loop
                time.sleep(.05)
                camNotReady = self.image_queue.empty() # wait for images ready
            
            dequeuedImage = self.image_queue.get() # get images formated as numpy from separate process queue
            self.writer.writeFrame(dequeuedImage)
            self.image_queue.task_done()
            

        
        
    def start(self, name="temp_video"):        
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record)
        self.video_thread.start()  


    def prepare(self, name="temp_video"):
        self.cam.BeginAcquisition()
        im = self.cam.GetNextImage(1000)
        self.frameSize = (im.GetWidth(), im.GetHeight())
        self.video_filename ="{}_flir_{}.mp4".format(name, time.time())    
        # self.video_out = cv2.VideoWriter(self.video_filename, self.fourcc,
        #                                  self.fps, self.frameSize)
        self.outlet = self.createOutlet(self.video_filename)
        self.streaming = True

        # setup output video file parameters (can try H265 in future for better compression):  
        # for some reason FFMPEG takes exponentially longer to write at nonstandard frame rates, so just use default 25fps and change elsewhere if needed
        self.FRAME_RATE_OUT = self.cam.AcquisitionResultingFrameRate()
        print('frame rate = {:.2f} FPS'.format(self.FRAME_RATE_OUT ))
        self.crfOut = 21 #controls tradeoff between quality and storage, see https://trac.ffmpeg.org/wiki/Encode/H.264 
        ffmpegThreads = 10 #this controls tradeoff between CPU usage and memory usage; video writes can take a long time if this value is low
        #crfOut = 18 #this should look nearly lossless
        # writer = skvideo.io.FFmpegWriter(movieName, outputdict={'-r': str(FRAME_RATE_OUT), '-vcodec': 'libx264', '-crf': str(crfOut)}) # with frame rate
        self.writer = skvideo.io.FFmpegWriter(self.video_filename, 
                outputdict={'-r': str(self.FRAME_RATE_OUT//2.4), '-vcodec': 'libx264', '-crf': str(self.crfOut)})#, '-threads': str(ffmpegThreads)})
        
        # fps = self.FRAME_RATE_OUT

        # crf = 17
        # self.writer = skvideo.io.FFmpegWriter(self.video_filename, 
        #             inputdict={ '-s':'{}x{}'.format(self.frameSize[0], self.frameSize[1])},
        #             outputdict={'-r': str(fps), '-c:v': 'libx264', '-crf': str(crf), '-preset': 'ultrafast', '-pix_fmt': 'yuv444p'})
        
        
    def record(self):   
        self.recording = True
        self.frame_counter = 0
        self.save_thread = threading.Thread(target=self.camCaptureVid)
        self.save_thread.start() 
        print(f"FLIR recording {self.video_filename}")
        t0 = time.time()
        self.stamp = []
        while self.recording:   
            im = self.cam.GetNextImage(1000)
            tsmp = im.GetTimeStamp()
            im_conv = im.Convert(PySpin.PixelFormat_BGR8, PySpin.HQ_LINEAR)
            im_conv_d = im_conv.GetData()
            im_conv_d = im_conv_d.reshape((im.GetHeight(), im.GetWidth(), 3) )
            self.image_queue.put(im_conv_d)
            #   stamp.append(time.time_ns())
            self.stamp.append(tsmp)
            
            #  Release image
            #
            #  *** NOTES ***
            #  Images retrieved directly from the camera (i.e. non-converted
            #  images) need to be released in order to keep from filling the
            #  buffer.
            im.Release()


            try:
                self.outlet.push_sample([self.frame_counter, tsmp])
            except:  # "OSError" from C++
                print(f"Reopening FLIR {self.device_index} stream already closed")
                self.outlet = self.createOutlet(self.video_filename)
                self.outlet.push_sample([self.frame_counter])

            # self.video_out.write(im_conv_d)
            self.frame_counter += 1
            
            if not self.frame_counter % 200:
                print(f"Queue length is {self.image_queue.qsize()} frame count: {self.frame_counter}")
            

        print(f"FLIR recording ended with {self.frame_counter} frames in {time.time()-t0}")
        self.cam.EndAcquisition() 
        self.recording = False  
        self.save_thread.join()
        self.writer.close()
        print(f"FLIR video saving ended in {time.time()-t0} sec")
        # self.video_out.release()    

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

    ximi = VidRec_Flir()
    ximi.start()
    time.sleep(10)
    ximi.close()
    ximi.frameSize
