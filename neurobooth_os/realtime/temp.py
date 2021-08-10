# -*- coding: utf-8 -*-
"""
Created on Thu Feb 11 18:14:44 2021

@author: adona
"""
import os
import sys
import threading
import uuid
import cv2
from pylsl import StreamInfo, StreamOutlet
import time
from datetime import datetime


def createFrameOutlet(filename, cam_name, w, h):
     streamName = 'CamStream' + cam_name
     n_chans = w*h
     info = StreamInfo(name=streamName, type='camstream', channel_format='int8', channel_count=n_chans,
                       source_id=str(uuid.uuid4()))
     info.desc().append_child_value("size_w", str(w))
     info.desc().append_child_value("size_h", str(h))
     return StreamOutlet(info)
     
fps=30
w=640
h=480
cap = cv2.VideoCapture(0,  cv2.CAP_DSHOW)
isOpen = cap.isOpened()
# isFrame, _  = cap.read()
fps_i = fps
width_i = w
height_i = h

cap.set(cv2.CAP_PROP_FPS, fps)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)       

frame_outlet = createFrameOutlet(0, "0" , w, h)
        
frameCounter =0           
recording = True
while recording:
    ret, frame = cap.read()
    
    
    win = "winName"
    # cv2.imshow(win, frame)
    if not ret:
        print("ret closed")
        recording = False
    
    ## Add frame number to video
    cv2.putText(frame,  
    f'{frameCounter},  {datetime.now().strftime("%H:%M:%S.%f")}',  
    (0, 50),  
    cv2.FONT_HERSHEY_SIMPLEX , 1,  
    (0, 0, 0), 2, cv2.LINE_4) 
    # cv2.imshow(win, frame)
    
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  
    frame_outlet.push_sample(frame.flatten())     
    frameCounter += 1
    
    cv2.waitKey(1) 

 

    

 
from datetime import datetime
import pylsl
import pyqtgraph.ptime as ptime
from pylsl import StreamInlet, resolve_stream
import numpy as np


streams = pylsl.resolve_streams()
inlet = StreamInlet(streams[0], max_buflen=1)

win = "winName"

buffer = []
while True:
    # sample, timestamp = inlet.pull_sample(timeout=0.0, sample=1)
        
    
    sample, timestamp = inlet.pull_sample(timeout=0.0)
    
    if sample is None:
        cv2.waitKey(1) 
        continue
        
    img_frame = np.array(sample, dtype=np.uint8).reshape(480, 640)
    
    cv2.putText(img_frame,  
    f'    {datetime.now().strftime("%H:%M:%S.%f")}',  
    (0, 75),  
    cv2.FONT_HERSHEY_SIMPLEX , 1,  
    (0, 0, 0), 2, cv2.LINE_4) 
    
    cv2.imshow(win, img_frame)
    
    cv2.waitKey(1) 





from pyqtgraph.Qt import QtGui, QtCore
import numpy as np
import pyqtgraph as pg

app = QtGui.QApplication([])

## Create window with GraphicsView widget
win = pg.GraphicsLayoutWidget()
win.show()  ## show widget alone in its own window
win.setWindowTitle('pyqtgraph example: ImageItem')
view = win.addViewBox()


## lock the aspect ratio so pixels are always square
view.setAspectLocked(True)

## Create image item
img = pg.ImageItem(border='w')
view.addItem(img)


## Set initial view bounds
view.setRange(QtCore.QRectF(0, 0, 600, 600))

## Create random image
streams = pylsl.resolve_streams()
inlet = StreamInlet(streams[0], max_buflen=1)

data, img_time = inlet.pull_sample()
data = np.array(data, dtype=np.uint8).reshape(480, 640).T[:, ::-1]
img.setImage(data)

i = 0

updateTime = ptime.time()
fps = 0



def updateData():
    global img, data, i, updateTime, fps

    ## Display the data
    
    img_frame, img_time = inlet.pull_sample(timeout=0.0)

    img_frame = np.array(img_frame, dtype=np.uint8).reshape(480, 640)
    
    
    cv2.putText(img_frame,  
    f'    {datetime.now().strftime("%H:%M:%S.%f")}',  
    (0, 75),  
    cv2.FONT_HERSHEY_SIMPLEX , 1,  
    (0, 0, 0), 2, cv2.LINE_4) 
    
    
    img.setImage(img_frame.T[:, ::-1])
    i = (i+1) % data.shape[0]

    QtCore.QTimer.singleShot(1, updateData)
    now = ptime.time()
    fps2 = 1.0 / (now-updateTime)
    updateTime = now
    fps = fps * 0.9 + fps2 * 0.1
    
    print ("%0.1f fps" % fps)
    

updateData()





