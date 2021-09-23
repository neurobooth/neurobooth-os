# -*- coding: utf-8 -*-
"""
Created on Mon May 10 13:01:13 2021

@author: ACQ
"""

import numpy as np
import cv2
import pyrealsense2 as rs

import neurobooth_os.iout.dshowcapture as dshowcapture

video_cap = dshowcapture.DShowCapture()
ndevs = video_cap.get_devices()
print(f"There are {ndevs} devices")

inf = video_cap.get_info()
for f in inf:
    print(f['index'], f['name'])
    # for cap in f['caps']:
    #     print(cap['id'], int(10000000 / cap['minInterval']))
    
ctx = rs.context()
devices = ctx.query_devices()
for dev in devices:
    print (dev)
    
dinx = 0
cap = cv2.VideoCapture(dinx, cv2.CAP_DSHOW)

keys_index = {ord(str(d)):d for d in range(ndevs)}

while(True):
    # Capture frame-by-frame
    ret, frame = cap.read()

    # Display the resulting frame
    if frame is not None:
        cv2.imshow('frame',frame)

    key = cv2.waitKey(1)
    if key == ord('q'):
        break
    
    elif key in list(keys_index.keys()):
        dinx_o = dinx 
        dinx = keys_index[key]
        print(f"Changing to {dinx}")
        cap = cv2.VideoCapture(dinx, cv2.CAP_DSHOW)
        ret, frame = cap.read()
        if frame is None:
            print(f"Frame cam {dinx} not available, going back")
            dinx = dinx_o 
            cap = cv2.VideoCapture(dinx, cv2.CAP_DSHOW)
        
    
# When everything done, release the capture
cap.release()
cv2.destroyAllWindows()


if 0:
    video_cap = dshowcapture.DShowCapture()
    dev_info = video_cap.get_info()

    video_cap.capture_device_by_dcap(0, 33, 1280,720, 90)
    
    {'id': 0,
     'name': 'Intel(R) RealSense(TM) Depth Camera 455  RGB',
     'path': '\\\\?\\usb#vid_8086&pid_0b5c&mi_03#6&2f5a5eb9&0&0003#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\\global',
     'caps': [{'id': 0,
       'minCX': 424,
       'minCY': 240,
       'maxCX': 424,
       'maxCY': 240,
       'granularityCX': 1,
       'granularityCY': 1,
       'minInterval': 111111,
       'maxInterval': 2000000,
       'rating': 2,
       'format': 301},
      {'id': 1,
       'minCX': 480,
       'minCY': 270,
       'maxCX': 480,
       'maxCY': 270,
       'granularityCX': 1,
       'granularityCY': 1,
       'minInterval': 111111,
       'maxInterval': 2000000,
       'rating': 2,
       'format': 301},
      {'id': 2,
       'minCX': 640,
       'minCY': 360,
       'maxCX': 640,
       'maxCY': 360,
       'granularityCX': 1,
       'granularityCY': 1,
       'minInterval': 111111,
       'maxInterval': 2000000,
       'rating': 2,
       'format': 301},
      {'id': 3,
       'minCX': 640,
       'minCY': 480,
       'maxCX': 640,
       'maxCY': 480,
       'granularityCX': 1,
       'granularityCY': 1,
       'minInterval': 166666,
       'maxInterval': 2000000,
       'rating': 2,
       'format': 301},
      {'id': 4,
       'minCX': 848,
       'minCY': 480,
       'maxCX': 848,
       'maxCY': 480,
       'granularityCX': 1,
       'granularityCY': 1,
       'minInterval': 166666,
       'maxInterval': 2000000,
       'rating': 2,
       'format': 301},
      {'id': 5,
       'minCX': 1280,
       'minCY': 720,
       'maxCX': 1280,
       'maxCY': 720,
       'granularityCX': 1,
       'granularityCY': 1,
       'minInterval': 333333,
       'maxInterval': 2000000,
       'rating': 2,
       'format': 301},
      {'id': 6,
       'minCX': 1280,
       'minCY': 800,
       'maxCX': 1280,
       'maxCY': 800,
       'granularityCX': 1,
       'granularityCY': 1,
       'minInterval': 333333,
       'maxInterval': 2000000,
       'rating': 2,
       'format': 301}],
     'type': 'DirectShow',
     'index': 0}
    
    
    import dshowcapture
    import numpy as np
    import cv2
    import pyrealsense2 as rs
    
    ctx = rs.context()
    devices = ctx.query_devices()
    for dev in devices:
        print (dev)