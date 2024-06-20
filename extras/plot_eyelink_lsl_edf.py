# -*- coding: utf-8 -*-
"""
Created on Mon May  9 14:15:36 2022

@author: STM
"""


from h5io import read_hdf5
import matplotlib.pyplot as plt
import numpy as np
import glob
import os.path as op

# session = '100080_2022-05-09' # MOT 1 ms wait, DSC no keyrelease
lsl_session = "72_2022-05-17"

f_ascs = glob.glob(f"Z:/data/{lsl_session}/{lsl_session}_*.asc")


for f_asc in f_ascs:
    fname = f_asc.replace(".asc", "_R001-Eyelink_1-Eyelink_sens_1.hdf5")
    task = f_asc.split("_")[-2]

    _, task_id = op.split(f_asc)
    print("\n", task_id)

    with open(f_asc, "r") as f:
        edf = f.readlines()

    events = [
        e.replace("MSG\t", "").replace("\n", "")
        for e in edf
        if "!V TARGET_POS target" in e
    ]

    # get timestamp, x, y
    events = [
        [
            e.split(" ")[0],
            e.split(", ")[0].split(" ")[-1],
            e.split(", ")[1].split(" ")[0],
        ]
        for e in events
    ]
    events = np.array(events, dtype=float)

    if not events.size:
        continue

    # to seconds
    events[:, 0] /= 1000

    smpls = [e.replace("\n", "").replace("   .", "").split("\t") for e in edf]
    smpls = [e for e in smpls if e[0].isdigit()]

    # get just relevant columns (time, R x, R y, L x, L y)
    smpls = [[e[:3] + e[4:6]] for e in smpls]
    smpls = [[c if c != "" else np.nan for c in r[0]] for r in smpls]
    smpls = np.array(smpls, dtype=float)
    # to seconds
    smpls[:, 0] /= 1000

    smpl_valid = [
        i for i, v in enumerate(smpls) if not np.isnan(v[1]) and not np.isnan(v[3])
    ]
    valit_1st = smpl_valid[0]
    valit_lst = smpl_valid[-1]

    data = read_hdf5(fname)

    dev_data_ts = data["device_data"]["time_series"][:, [0, 1, 3, 4, 11, 12]]
    dev_data_stmps = data["device_data"]["time_stamps"]

    marker_ts = data["marker"]["time_series"]
    marker_stmps = data["marker"]["time_stamps"]

    # only taget pos markers
    marker_stmps = [
        s for (s, t) in zip(marker_stmps, marker_ts) if "!V TARGET_POS" in t[0]
    ]
    marker_ts = [t for t in marker_ts if "!V TARGET_POS" in t[0]]
    marker_ts = [
        [
            e[0].split("_")[-1],
            e[0].split(", ")[0].split(" ")[-1],
            e[0].split(", ")[1].split(" ")[0],
        ]
        for e in marker_ts
    ]
    marker_ts = np.array(marker_ts, dtype=float)

    print(f"Eyelink has {len(smpls)} samples, LSL {len(dev_data_ts)} samples")
    print(f"Eyelink has {events.shape[0]} events, LSL {marker_ts.shape[0]} events")

    # Align clock
    eyelk_offset = events[0][0] - marker_stmps[0]
    # eyelk_offset = smpls[0,0] - dev_data_stmps[0]
    events[:, 0] -= eyelk_offset
    smpls[:, 0] -= eyelk_offset

    marker_ts[:, 0] -= marker_ts[0, 0] - marker_stmps[0]

    tdiff = events[:, 0] - marker_stmps
    print(
        f"  diff Eyelink and LSL time stamps Mean {np.mean(tdiff)}, max {np.max(tdiff)} min {np.min(tdiff)}"
    )

    tdiff = events[:, 0] - marker_ts[:, 0]
    print(
        f"  diff Eyelink and Unix time stamps Mean {np.mean(tdiff)}, max {np.max(tdiff)} min {np.min(tdiff)}"
    )

    print(
        f"EDF FS: {np.median(1/np.diff(smpls[:,0]))}, LSL FS: {np.median(1/np.diff(dev_data_stmps))}"
    )

    # smpls[:,0] -= smpls[0,0]
    # dev_data_stmps[:] -= dev_data_stmps[0]
    # events[:,0] -= events[0,0]
    # marker_stmps[:] -= marker_stmps[0]

    plt.figure()

    plt.plot(dev_data_stmps, dev_data_ts[:, 0], alpha=0.5, label="Gaze_R_x_LSL")
    plt.plot(smpls[:, 0], smpls[:, 3], alpha=0.5, label="Gaze_R_x_ET")
    plt.plot(dev_data_stmps, dev_data_ts[:, 2], alpha=0.5, label="Gaze_L_x_LSL")
    plt.plot(smpls[:, 0], smpls[:, 1], alpha=0.5, label="Gaze_L_x_ET")

    if "pursuit" in task or "mouse" in task:
        plt.plot(marker_stmps, marker_ts[:, 1], alpha=0.5, label="mrkr_x_LSL")
        plt.plot(events[:, 0], events[:, 1], alpha=0.5, label="mrkr_x_ET")
    else:
        plt.plot(marker_stmps, marker_ts[:, 1], "*", alpha=0.5, label="mrkr_x_LSL")
        plt.plot(events[:, 0], events[:, 1], "*", alpha=0.5, label="mrkr_x_ET")

    plt.plot(
        dev_data_stmps[1:],
        np.diff(dev_data_ts[:, -2]) * 100,
        alpha=0.5,
        label="lsl_ET_time diff",
    )
    plt.title(task_id)
    plt.legend()
    plt.show(block=False)

    plt.gca().invert_yaxis()


# plt.figure()


# if 'pursuit' in task or 'mouse' in task:
#     plt.plot(marker_stmps, marker_ts[:,1], alpha=.5,label='mrkr_x_LSL')
#     plt.plot(events[:,0], events[:,1], alpha=.5, label='mrkr_x_ET')
# else:
#     plt.plot(marker_stmps, marker_ts[:,1], "*", alpha=.5,label='mrkr_x_LSL')
#     plt.plot(events[:,0], events[:,1], "*", alpha=.5, label='mrkr_x_ET')

# plt.plot( dev_data_stmps[1:], np.diff(dev_data_ts[:,-2])*100, alpha=.5, label='lsl_ET_time diff')

# plt.legend()
# plt.show(block=False)
# plt.title(f"{task}_{task_time}")
# plt.gca().invert_yaxis()


# dd = np.diff(dev_data_stmps)
# de = np.diff(smpls[:,0])


# plt.figure()

# plt.plot( dev_data_stmps[1:], np.diff(dev_data_ts[:,-2])/1000, alpha=.5, label='lsl_ET_time diff')
# plt.plot( dev_data_stmps[1:], np.diff(dev_data_stmps), alpha=.5, label='lsl_tstmps diff')

# plt.plot( smpls[1:,0], np.diff(smpls[:,0]), alpha=.5, label='ET_tstmps diff')

# plt.legend()


# ts_et = dev_data_ts[:,-2]/1000


# with open(f_asc, 'r') as f:
#     edf = f.readlines()

# events = [e.replace("MSG\t", "").replace('\n', "") for e in edf if '!V TARGET_POS target' in e]

# # get timestamp, x, y
# events = [[e.split(" ")[0], e.split(", ")[0].split(" ")[-1],  e.split(", ")[1].split(" ")[0]] for e in events]
# events = np.array(events, dtype=float)
# # to seconds
# events[:,0] /= 1000


# smpls = [e.replace('\n', "").replace('   .', "").split('\t') for e in edf ]
# smpls = [e for e in smpls if e[0].isdigit()]

# # get just relevant columns (time, R x, R y, L x, L y)
# smpls = [[e[:3] + e[4:6]] for e in smpls]
# smpls = [[c if c!="" else np.nan for c in r[0]] for r in smpls]
# smpls = np.array(smpls, dtype=float)
# # to seconds
# smpls[:,0] /= 1000

# plt.figure()

# plt.plot(ts_et, dev_data_ts[:,0], alpha=.5, label='Gaze_R_x_LSL')
# plt.plot(smpls[:,0], smpls[:,1],  alpha=.5,label='Gaze_R_x_ET')
