# -*- coding: utf-8 -*-
"""
Created on Mon Dec 14 09:00:21 2020

@author: adona
"""
import pyxdf
import cv2
import pyaudio
import config

import matplotlib.pyplot as plt
import numpy as np


def read_vid(cap):
    vid_mat = []
    f_num = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # vid_mat.append(np.average(frame,2))
        vid_mat.append(np.average(frame))
        f_num += 1

    # vid_mat = np.stack(vid_mat, 2)
    return vid_mat, f_num


def crop_frame(vid_mat, dims):
    # dims = x1, y1, x2, y2

    vd = vid_mat[dims[1]:dims[3], dims[0]:dims[2], :]

    return vd


def plot_frames(vid_mat_list, frame_nums):

    n_cams = len(vid_mat_list)
    fig, axs = plt.subplots(1, n_cams)

    for ax, cap, frame_num in zip(axs, vid_mat_list, frame_nums):
        frame = cap[:, :, frame_num]
        ax.imshow(frame)


def plot_averg(vid_crp_list, frame_events_list):

    n_cams = len(vid_crp_list)
    fig, axs = plt.subplots(n_cams, 1)

    for ax, cap, evts in zip(axs, vid_crp_list, frame_events_list):
        cap_m = cap  # np.mean(cap,(0,1))
        for ev in evts:
            ax.axvline(ev)

        ax.plot(cap_m, ".-")


def find_closest(marker_stmp, vid_stmps):
    inx = np.argmin(np.abs(vid_stmps['time_stamps'] - marker_stmp))
    frame_num, = vid_stmps['time_series'][inx]
    return int(frame_num)


def sound(array, fs=43):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=len(
        array.shape), rate=fs, output=True)
    stream.write(array.tobytes())
    stream.stop_stream()
    stream.close()
    p.terminate()


def record(duration=3, fs=44100):
    nsamples = duration * fs
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=fs, input=True,
                    frames_per_buffer=nsamples)
    buffer = stream.read(nsamples)
    array = np.frombuffer(buffer, dtype='int16')
    stream.stop_stream()
    stream.close()
    p.terminate()
    return array


sess_name = 'tt__timing_task'
file = config.paths["data_out"] + sess_name + ".xdf"

data, header = pyxdf.load_xdf(file)


for ch in data:
    print(ch['info']['name'])
    if ch['info']['name'][0] == 'Marker':
        markers = ch
    elif ch['info']['name'][0] == 'BrioFrameIndex_7':
        cam1 = ch
    elif ch['info']['name'][0] == 'VideoFrameIndex_2':
        cam2 = ch
    elif ch['info']['name'][0] == 'Tobii':
        tobii = ch
    elif ch['info']['name'][0] == 'Audio':
        audio = ch
    elif ch['info']['name'][0] == 'Mouse':
        mouse = ch

# data[0]['time_stamps'].size/ (data[0]['time_stamps'][-1] - data[0]['time_stamps'][0])

###############################################################################
# Video
####

# vid1=  config.paths["nas"] + sess_name + 'brio1.avi'
# vid2=  config.paths["nas"] + sess_name + 'brio2.avi'

# vid1=  config.paths["nas"] +"tt_timing_task_brio1_1622237533.659113.avi"
# vid2=  config.paths["nas"] +"tt_timing_task_brio2_1622237533.6628437.avi"
vid1 = config.paths["nas"] + "tt_timing_task_brio7_1622838867.7885964.avi"

# vid1= 'C:\\Users\\adona\\Desktop\\neurobooth\\software\\neurobooth_data\\demo01_FingerTapping_cam_0.avi'
# vid2= 'C:\\Users\\adona\\Desktop\\neurobooth\\software\\neurobooth_data\\demo01_FingerTapping_cam_1.avi'


cap1 = cv2.VideoCapture(vid1)
cap2 = cv2.VideoCapture(vid2)

vid_mat1, _ = read_vid(cap1)
vid_mat2, _ = read_vid(cap2)


frame_nums = [find_closest(markers['time_stamps'][0], cam1),
              find_closest(markers['time_stamps'][0], cam2)]

plot_frames([vid_mat1, vid_mat2], frame_nums)


crops_vals1 = [512, 156, 545, 179]  # x, y,x2, y2
crops_vals2 = [513, 155, 544, 180]  # x, y, x2, y2

vid_crp1 = crop_frame(vid_mat1, crops_vals1)
vid_crp2 = crop_frame(vid_mat2, crops_vals2)

# plot_frames([vid_crp1, vid_crp2], frame_nums)
frm_events = [[find_closest(m, vid) for m in markers['time_stamps']]
              for vid in [cam1, cam2]]

plot_averg([vid_crp1, vid_crp2], frm_events)


###############################################################################
# Audio
####

evts = [np.argmin(np.abs(audio['time_stamps'] - e))
        for e in markers['time_stamps']]
audio_data = np.hstack(audio['time_series'][evts[0]:, :])
plt.figure(), plt.plot(np.hstack(audio['time_series'][evts[0]:, :]))

[plt.axvline((e - evts[0]) * 1024, color='r') for e in evts]


#####################

sound(audio_data, fs=44100)


#

#####################

# 6/4


tsmp = cam1['time_stamps']
tmax = len(tsmp)

vid_mat1 = np.array(vid_mat1)[cam1['time_series']]
plt.figure(), plt.plot(tsmp, (vid_mat1 - vid_mat1.mean()) / vid_mat1.std())

audio_data = audio['time_series'][evts[0]:, :].max(1)
tsmp_a = audio['time_stamps']
tmax = len(audio_data)

plt.plot(tsmp_a[:tmax], (audio_data - audio_data.mean()) / audio_data.std())

tt = markers['time_stamps']
plt.vlines(tt, -4, 4, "red")


tsmp = cam1['time_stamps']
tinx = cam1['time_series']

plt.figure(), plt.plot(tsmp, tinx)
plt.title("frame number vs LsL timestamp")

tsmp0 = tsmp
tsmp0 -= tsmp[0]
tinx0 = tinx
tinx0 -= tinx[0]
plt.figure(), plt.plot(tsmp0, tinx0)
plt.title("frame index vs LsL index")
