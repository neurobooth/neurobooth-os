import os
from h5io import read_hdf5
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def _get_target_traces(mdata):
    ts_ix = []
    x_coord = []
    y_coord = []
    for ix, txt in enumerate(mdata['time_series']):
        if '!V TARGET_POS' in txt[0]:
            ts_ix.append(ix)
            l = txt[0].split(' ')
            x_coord.append(int(l[3][:-1]))
            y_coord.append(int(l[4]))

    ctrl_ts = mdata['time_stamps'][ts_ix]
    return ctrl_ts, x_coord, y_coord

def _get_mrk_traces(mdata):
    ts_ix = []
    for ix, txt in enumerate(mdata['time_series']):
        if 'Trial_start' in txt[0]:
            ts_ix.append(ix)
           
    ctrl_ts = mdata['time_stamps'][ts_ix]
    return ctrl_ts
#path = r'C:\Users\siddh\Desktop\lab_projects\Neurobooth_Explorer\data'
#proc_data_path = r'C:\Users\siddh\Desktop\lab_projects\Neurobooth_Explorer\processed_data'



path = r'Z:\data'
proc_data_path = 'Z:\processed_data'
session_id = '100064_2022-06-17'
session_time = '_15h-12m-06s'


# session_time = '_15h-01m-19s'

fnames = []
for (dirpath, dirnames, filenames) in os.walk(os.path.join(path, session_id)):
    fnames.extend(filenames)
    break
timing_test_files = [fname for fname in fnames if session_time in fname ]

fnames = []
for (dirpath, dirnames, filenames) in os.walk(os.path.join(proc_data_path, session_id)):
    fnames.extend(filenames)
    break
rgb_files = [fname for fname in fnames if session_time in fname ]

devices=["Eyelink", "Mic"]
data = dict()
for device in devices:
    for file in timing_test_files:
        if device in file:
            data.update({device: read_hdf5(os.path.join(path, session_id, file))})

devices = ['Intel_D455_1', 'Intel_D455_2', 'Intel_D455_3']
for device in devices:
    for file in rgb_files:
        if device in file:
            data.update({device: read_hdf5(os.path.join(proc_data_path, session_id, file))})

data_cols=dict()
data_cols['Eyelink'] = [0]#,1,3,4]
data_cols['Intel_D455_1'] = [0,1,2]
data_cols['Intel_D455_2'] = [0,1,2]
data_cols['Intel_D455_3'] = [0,1,2]
data_cols['Mic'] = []
data_cols['Mbient_RH'] = [1,2,3]

legend_dict=dict()
legend_dict['Eyelink'] = ['R_gazeX']#, 'R_gazeY', 'L_gazeX', 'L_gazeY',]
legend_dict['Intel_D455_1'] = ['R', 'G', 'B']
legend_dict['Intel_D455_2'] = ['R', 'G', 'B']
legend_dict['Intel_D455_3'] = ['R', 'G', 'B']
legend_dict['Mic'] = ['amplitude']

fig, ax = plt.subplots(1, sharex=True, figsize=[20,5])

for ix,ky in enumerate(data.keys()):
    if ky == "Eyelink":
        ax.plot(data[ky]['device_data']['time_stamps'], data[ky]['device_data']['time_series'][:, data_cols[ky]], color='magenta', label='R_gaze_X')
        marker_ts, target_x, target_y = _get_target_traces(data[ky]['marker'])
        
        trig_ts = _get_mrk_traces(data[ky]['marker'])
        ax.plot(marker_ts, target_x, drawstyle='steps-post', ls='--', label='Target_X', color='black')
        
        for tx in trig_ts:
            ax.axvline(tx)
        #ax.plot(marker_ts, target_y, drawstyle='steps-post', ls='--', label='Target_Y', color='')
    if ky == "Mbient_RH":
        ax.plot(data[ky]['device_data']['time_stamps'], data[ky]['device_data']['time_series'][:, data_cols[ky]], color='magenta', label='R_gaze_X')
        marker_ts, target_x, target_y = _get_target_traces(data[ky]['marker'])
        
        trig_ts = _get_mrk_traces(data[ky]['marker'])
        ax.plot(marker_ts, target_x, drawstyle='steps-post', ls='--', label='Target_X', color='black')
        
        for tx in trig_ts:
            ax.axvline(tx)
        #ax.plot(marker_ts, target_y, drawstyle='steps-post', ls='--', label='Target_Y', color='')
    if ky == "Mic":
        # read audio data
        audio_tstmp = data[ky]['device_data']['time_stamps']
        audio_ts = data[ky]['device_data']['time_series']
        chunk_len = audio_ts.shape[1]
        
        if chunk_len %2:
            chunk_len -= 1
            time_mic = [ t[0] for t in audio_ts]
            audio_ts = audio_ts[:, 1:]
            ax.plot(audio_tstmp,time_mic, 'y--', label='audio clock')
            

        # restructure audio data
        audio_tstmp = np.insert(audio_tstmp, 0, audio_tstmp[0] - np.diff(audio_tstmp).mean())
        tstmps = []
        for i in range(audio_ts.shape[0]):
            tstmps.append(np.linspace(audio_tstmp[i], audio_tstmp[i+1], chunk_len))
        audio_tstmp_full = np.hstack(tstmps)
        audio_ts_full = np.hstack(audio_ts)

        # plot audio data
        ax.plot(audio_tstmp_full, audio_ts_full+1000, label='Amplitude', alpha=0.5)
    if "Intel_D455_2" in ky:
        ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 0]-np.nanmean(data[ky]['device_data']['time_series'][:, 0])+20)*50, color='red', label='red 2')
        ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 1]-np.nanmean(data[ky]['device_data']['time_series'][:, 1])+20)*50, color='green', label='green 2')
        ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 2]-np.nanmean(data[ky]['device_data']['time_series'][:, 2])+20)*50, color='blue', label='blue 2')
    if "Intel_D455_9" in ky:
        ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 0]-np.nanmean(data[ky]['device_data']['time_series'][:, 0])+50)*20, color='darkred', label='red 3')
        ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 1]-np.nanmean(data[ky]['device_data']['time_series'][:, 1])+50)*20, color='darkgreen', label='green 3')
        ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 2]-np.nanmean(data[ky]['device_data']['time_series'][:, 2])+50)*20, color='darkblue', label='blue 3')



ax.legend()
plt.show()