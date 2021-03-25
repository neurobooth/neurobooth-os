import os
import sys
import threading
import uuid
import cv2
from pylsl import StreamInfo, StreamOutlet
import dshowcapture
import time
import functools
import warnings
warnings.filterwarnings('ignore')


def catch_exception(f):
    @functools.wraps(f)
    def func(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print('Caught an exception in function "{}" of type {}'.format(f.__name__, e))
    return func


class VidRec_Brio():        
    def __init__(self,  fourcc=cv2.VideoWriter_fourcc(*'MJPG'), sizex=1280, sizey=720,
                 fps=90, camindex=0, mode=33, doPreview=False):
        
        self.open = True
        self.doPreview = doPreview
        self.previewing = True
        
        self.device_index = camindex
        self.fps = fps                  # fps should be the minimum constant rate at which the camera can
        self.fourcc = fourcc            # capture images (with no decrease in speed over time; testing is required)
        self.frameSize = (sizex, sizey) # video formats and sizes also depend and vary according to the camera used
        self.video_cap = dshowcapture.DShowCapture()
        self.video_cap.capture_device_by_dcap(self.device_index, mode, self.frameSize[0], self.frameSize[1], self.fps)

        if doPreview:
            self.preview_fps = 10
            info_stream = StreamInfo('Webcam', 'Experiment', 320 * 240,  self.preview_fps, 'int32', 'webcamid_2')
            self.outlet_preview = StreamOutlet(info_stream)
            self.preview_start()
            self.preview_relFps = round(fps/self.preview_fps)
            
            
    
    def preview(self):
        "Streams camera content while not recording to file"
        while self.previewing == True:
            frame = self.video_cap.get_frame(1000)
            if frame is not None:
                frame = self.frame_preview(frame)
            self.outlet_preview.push_sample(frame.flatten())
            
            key = cv2.waitKey(20)
            if key == 27: # exit on ESC
                break
            
            time.sleep(1/self.preview_fps)
        
    def frame_preview(self, frame):        
        frame = cv2.resize(frame,(320, 240))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    def preview_start(self):
        if self.doPreview:
            self.previewing = True
            self.preview_thread = threading.Thread(target=self.preview)
            self.preview_thread.start()


    def prepare(self, name="temp_video.avi"):
        self.video_filename = name
        self.video_out = cv2.VideoWriter(self.video_filename, self.fourcc, self.fps, self.frameSize)
        self.frame_counter = 0
        self.outlet = self.createOutlet(self.video_filename)

    
    @catch_exception
    def record(self):
        self.previewing = False
        self.recording = True
        while self.recording:
            if self.video_cap.capturing():
                self.frame_counter += 1
                frame = self.video_cap.get_frame(1000)
                self.outlet.push_sample([self.frame_counter])                
                self.video_out.write(frame)
            
                if self.doPreview:
                    # Push frame every relative Fps
                    if (self.frame_counter % self.preview_relFps) == 0:
                        frame = self.frame_preview(frame)
                        self.outlet_preview.push_sample(frame.flatten())

    @catch_exception
    def stop(self):
        if self.open:
            self.recording = False
            # print("total frame = {}".format(self.frame_counter))         
            self.preview_start()
            


    @catch_exception
    def start(self):
        self.video_thread = threading.Thread(target=self.record)
        self.video_thread.start()     
        

    @catch_exception        
    def close(self):
        self.previewing = False
        self.recording = False
        self.video_out.release()
        self.video_cap.stop_capture()
        self.video_cap.destroy_capture()
        

    @catch_exception        
    def createOutlet(self, filename,cam_name):
        streamName = 'VideoFrameIndex' + cam_name
        info = StreamInfo(name=streamName, type='videostream', channel_format='int32', channel_count=1,
                          source_id=str(uuid.uuid4()))
        
        info.desc().append_child_value("videoFile", filename)
        return StreamOutlet(info)
    
    
# if __name__ == "__main__":
#     cam_dict = [{'name': 'cam_0', 'index': 0}]
#     record_dir = r'C:\git\neurobooth-eel'
#     participant='Montag'
#     videocapture = ViedoCapture(cam_dict)
#     videocapture.init(record_dir, participant)
#     ##self.videocapture.stopRecording()
#     cap = threading.Thread(target=videocapture.capture)
#     cap.start()