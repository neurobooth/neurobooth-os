# -*- coding: utf-8 -*-
"""
Created on Mon May 10 13:01:13 2021

@author: ACQ
"""

from iout import dshowcapture
import numpy as np
import cv2
import pyrealsense2 as rs


video_cap = dshowcapture.DShowCapture()
ndevs = video_cap.get_devices()
print(f"There are {ndevs} devices")

inf = video_cap.get_info()
for f in inf:
    print(f['index'], f['name'])
    
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

