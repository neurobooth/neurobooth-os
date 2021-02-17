# -*- coding: utf-8 -*-
"""
Created on Wed Nov 25 08:31:29 2020

@author: adona
"""
import os
import sys
import threading
import uuid
import cv2
from pylsl import StreamInfo, StreamOutlet



class ViedoCapture():
    recording = False
    
    def __init__(self, cam_dict):
        self.cap = []
        self.writers = []
        self.outlets = []
        self.frameCounter = 0
        self.recording = False
        self.showUI = False
        self.winNames = []
        self.cam = cam_dict
        
    def init(self, filepath, description):
        self.filepath = filepath
        ## creates the settings; creates the stream
        cam = self.cam
        filename = description + '_' + cam['name'] + '.avi'
        cap_i = cv2.VideoCapture(cam['index'],  cv2.CAP_DSHOW)
        
        self.isOpen = cap_i.isOpened()
  
        # Ui-Information
        if self.showUI:
            self.winName = 'Camera ' + str(cam['index'])
            cv2.namedWindow(self.winName)
            
        cap_i.set(cv2.CAP_PROP_FPS, 30)
        cap_i.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap_i.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        fps = cap_i.get(cv2.CAP_PROP_FPS)
        width = cap_i.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = cap_i.get(cv2.CAP_PROP_FRAME_HEIGHT)
        filename = os.path.join(self.filepath, filename)
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        
        self.cap_i = cap_i
        self.writer_i = cv2.VideoWriter(filename, fourcc, fps, (int(width), int(height)))
        self.outlet = self.createOutlet(cam['index'], filename, cam['name'])
        
        print('width:' + str(width) + ' height:' + str(height) + 'fps:' + str(fps))
        # print('setup Cameras')
        
    def capture(self):
        self.recording = True
        
        try:
            while self.recording:
                ret, frame = self.cap_i.read()
                
                if self.showUI:
                    win_i = self.winName
                    cv2.imshow(win_i, frame)
                if not ret:
                    print("ret closed")
                    self.recording = False
                self.outlet.push_sample([self.frameCounter])
                
                cv2.putText(frame,  
                f'{self.frameCounter}',  
                (50, 50),  
                cv2.FONT_HERSHEY_SIMPLEX , 1,  
                (0, 255, 255),  
                2,  
                cv2.LINE_4) 
                
                self.writer_i.write(frame)
                self.frameCounter += 1
                cv2.waitKey(1)
            print("Cam recording finished")
            
        finally:
            print('capturwegabrsdf')
            self.stopRecording()
            
             
    def stopRecording(self):
        self.recording = False
        self.cap_i.release()
        cv2.destroyAllWindows()
        
    def createOutlet(self, index, filename,cam_name):
        streamName = 'VideoFrameMarker' + cam_name
        info = StreamInfo(name=streamName, type='videostream', channel_format='float32', channel_count=1,
                          source_id=str(uuid.uuid4()))
        videoFile = filename
        if sys.platform == "linux":
            videoFile = os.path.splitext(filename)[0] + '.ogv'
        info.desc().append_child_value("videoFile", videoFile)
        return StreamOutlet(info)

def cameras_stream():  # TODO: add args for participant and directory
    record_dir = r'C:\Users\adona\Desktop\neurobooth'
    participant = 'test'
    
    vcaps = []
    for cID in range(2):
        cam_dict = {'name': f'cam_{cID}', 'index':cID}
        # print(f'cam_{cID} opening')
        videocapture = ViedoCapture(cam_dict)
        videocapture.init(record_dir, participant) 
        if videocapture.isOpen:
            print(f'cam_{cID} recording')
            cap = threading.Thread(target=videocapture.capture)     
            vcaps.append((cap, videocapture))
            
    return  vcaps

def cameras_start_rec(vcaps):
    for vcap in vcaps:
        vcap[0].start() 
    

#if __name__ == "__main__":
    # vcaps = cameras_stream()
    # cameras_start_rec(vcaps)
    
    # for vcap in vcaps:
    #     vcap[1].recording = False
#    cam_dict = {'name': 'cam_0', 'index': 1}
#    record_dir = r'C:\Users\adona\OneDrive\Desktop\Neurobooth'

#    participant='test'
#    videocapture = ViedoCapture(cam_dict)
#    videocapture.init(record_dir, participant) 

#    cap = threading.Thread(target=videocapture.capture)
#    cap.start()
