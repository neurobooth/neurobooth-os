# -*- coding: utf-8 -*-
"""
Created on Tue Apr 26 14:50:59 2022

@author: STM
"""

from h5io import read_hdf5
import glob
import os.path as op
import numpy as np

sess = "100080_2022-05-02"
fl = glob.glob(f'Z:/data/{sess}/{sess}*-Mbient_*-mbient_acc_1-mbient_gyro_1.hdf5')

file = 'Z:/data/72_2022-04-26/72_2022-04-26_12h-18m-10s_mouse_obs_R001-Mbient_LH_2-mbient_acc_1-mbient_gyro_1.hdf5'

for file in fl[9:]:
    data = read_hdf5(file)
    _, name = op.split(file)
    nsmpl = len(data['device_data']['time_series'])
    duration = data['device_data']['time_stamps'][-1] - data['device_data']['time_stamps'][0]
    name_print = name.replace(sess, "").replace("-mbient_acc_1-mbient_gyro_1.hdf5", '')
    if duration == 0:
        print(name_print, nsmpl, f"{duration :.2f}")
        continue
    fps = np.median(1/np.diff((data['device_data']['time_stamps'])))
    fps_m =  np.mean(1/np.diff((data['device_data']['time_stamps'])))
    
    fps_local = 1/np.median(np.diff(data['device_data']['time_series'][:,0]))
    print(name_print, nsmpl, f"{duration :.2f}, fps duration:{int(nsmpl/duration)}, fps:{int(fps)}, fps local:{int(fps_local)}, fps mean:{int(fps_m)}")


import matplotlib.pyplot as plt

tstmp = data['device_data']['time_series'][:,0]
tstmp_df = np.diff(tstmp)
plt.hist(tstmp_df, 1000)
plt.plot(tstmp_df)
plt.plot(data['device_data']['time_series'][:,1:4])
plt.plot(data['device_data']['time_series'][:,4:])





