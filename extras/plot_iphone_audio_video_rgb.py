# -*- coding: utf-8 -*-
"""
Created on Mon Aug  1 15:49:00 2022

@author: ACQ
"""

import moviepy.editor as mp
import numpy as np
import cv2
import json
from h5io import read_hdf5
import matplotlib.pyplot as plt

fname = 'Z:/data/100064_2022-09-28/100064_2022-09-28_14h-54m-26s_timing_test_obs_IPhone.mov'
h5 = 'Z:/data/100064_2022-09-28/100064_2022-09-28_14h-54m-26s_timing_test_obs_R001-IPhone_dev_1-IPhone_sens_1.hdf5'


my_clip = mp.VideoFileClip(fname)
audio =  my_clip.audio.to_soundarray()[:,0]
audio_ts = np.linspace(my_clip.audio.start, my_clip.audio.end, int( my_clip.audio.end*my_clip.audio.fps))


cap = cv2.VideoCapture(fname)
fps = cap.get(5)
vid_nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))


frame_means = np.zeros((vid_nframes, 3))
frame_means[:, :] = np.nan
frame_n = -1
frame_inxs = []

success = True
while success:
    success, img = cap.read()
    if not success:
        break

    frame_n += 1
    
    rgb_m = img.mean(0).mean(0)
        
    frame_means[frame_n] = rgb_m
    frame_inxs.append(frame_n)

with open(fname.replace('.mov', '.json'), "r") as f:
    data = json.load(f)
data = [eval(l) for l in data]

time_frames = np.zeros(len(data))
for ts in data:
    time_frames[int(ts['FrameNumber'])] = float(ts['Timestamp'])

print("First Json frame: ", time_frames[0])


lsldata = read_hdf5(h5)
lsl = lsldata['device_data']['time_series']

# check if first and second rows == same first frame number
if lsl[0,0] == lsl[1,0]:
    print("LSL start recording at: ",  lsl[0,1])
    print("LSL first frame at: ",  lsl[1,1])
    lsl = lsl[1:-1]

plt.figure()
plt.scatter(time_frames, lsl[:,1])
plt.title('json times and lsl iphone times')

plt.figure()
plt.plot(time_frames-lsl[:,1])
plt.title('json times minus lsl iphone times')


time_frames -= time_frames[0]

plt.figure()
plt.plot(audio_ts, audio*800+100)
plt.plot(time_frames, frame_means, '-.')
    
