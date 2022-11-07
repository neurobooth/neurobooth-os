import os
from h5io import read_hdf5
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from optparse import OptionParser

def _get_target_traces(mdata):
    ts_ix = []
    x_coord = []
    y_coord = []
    for ix, txt in enumerate(mdata["time_series"]):
        if "!V TARGET_POS" in txt[0]:
            ts_ix.append(ix)
            l = txt[0].split(" ")
            x_coord.append(int(l[3][:-1]))
            y_coord.append(int(l[4]))

    ctrl_ts = mdata["time_stamps"][ts_ix]
    return ctrl_ts, x_coord, y_coord


def _get_mrk_traces(mdata):
    ts_ix = []
    for ix, txt in enumerate(mdata["time_series"]):
        if "Trial_start" in txt[0]:
            ts_ix.append(ix)

    ctrl_ts = mdata["time_stamps"][ts_ix]
    return ctrl_ts


def normalize(x):
    return (x - np.nanmean(x)) / np.nanstd(x)


def offset(ts):
    # ts -= ts[0]
    return ts


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-p", "--path", dest="path", type="string", default="Z:/data/", help="Specify which timing test path to use")
    (options, args) = parser.parse_args()
    path = options.path
    # path = r'C:\Users\siddh\Desktop\lab_projects\Neurobooth_Explorer\data'
    # proc_data_path = r'C:\Users\siddh\Desktop\lab_projects\Neurobooth_Explorer\processed_data'


    # vid = 'Z:/data/100059_2022-07-08/100059_2022-07-08_15h-36m-32s_timing_test_obs_intel2.bag'
    path = r"Z:\data"
    proc_data_path = "Z:\processed_data"
    session_id = "100064_2022-09-28"
    session_time = "_14h-54m-26s"

    # session_time = '_14h-41m-51s'

    # session_id = '100059_2022-07-08'
    # session_time = '_15h-36m-32s'
    # session_time = '_15h-01m-19s'

    fnames = []
    for (dirpath, dirnames, filenames) in os.walk(os.path.join(path, session_id)):
        fnames.extend(filenames)
        break
    timing_test_files = [fname for fname in fnames if session_time in fname]

    fnames = []
    for (dirpath, dirnames, filenames) in os.walk(os.path.join(proc_data_path, session_id)):
        fnames.extend(filenames)
        break
    rgb_files = [fname for fname in fnames if session_time in fname]

    devices = ["Eyelink", "Mic"]
    data = dict()
    for device in devices:
        for file in timing_test_files:
            if device in file:
                data.update({device: read_hdf5(os.path.join(path, session_id, file))})

    devices = ["Intel_D455_1", "Intel_D455_2", "Intel_D455_3", "FLIR", "IPhone"]
    for device in devices:
        for file in rgb_files:
            if device in file:
                data.update(
                    {device: read_hdf5(os.path.join(proc_data_path, session_id, file))}
                )

    data_cols = dict()
    data_cols["Eyelink"] = [0]  # ,1,3,4]
    data_cols["Intel_D455_1"] = [0, 1, 2]
    data_cols["Intel_D455_2"] = [0, 1, 2]
    data_cols["Intel_D455_3"] = [0, 1, 2]
    data_cols["Flir"] = [0, 1, 2]
    data_cols["IPhone"] = [0, 1, 2]
    data_cols["Mic"] = []
    data_cols["Mbient_RH"] = [1, 2, 3]

    legend_dict = dict()
    legend_dict["Eyelink"] = ["R_gazeX"]  # , 'R_gazeY', 'L_gazeX', 'L_gazeY',]
    legend_dict["Intel_D455_1"] = ["R", "G", "B"]
    legend_dict["Intel_D455_2"] = ["R", "G", "B"]
    legend_dict["Intel_D455_3"] = ["R", "G", "B"]
    legend_dict["Flir"] = ["R", "G", "B"]
    legend_dict["IPhone"] = ["R", "G", "B"]
    legend_dict["Mic"] = ["amplitude"]

    fig, ax = plt.subplots(1, sharex=True, figsize=[20, 5])

    for ix, ky in enumerate(data.keys()):
        if ky == "Eyelink":
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, data_cols[ky]]),
                color="magenta",
                label="R_gaze_X",
            )
            marker_ts, target_x, target_y = _get_target_traces(data[ky]["marker"])

            trig_ts = _get_mrk_traces(data[ky]["marker"])
            ax.plot(
                offset(marker_ts),
                normalize(target_x),
                drawstyle="steps-post",
                ls="--",
                label="Target_X",
                color="black",
            )

            for tx in trig_ts:
                ax.axvline(tx)
            # ax.plot(marker_ts, target_y, drawstyle='steps-post', ls='--', label='Target_Y', color='')
        if ky == "Mbient_RH":
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, data_cols[ky]]),
                color="magenta",
                label="R_gaze_X",
            )
            marker_ts, target_x, target_y = _get_target_traces(data[ky]["marker"])

            trig_ts = _get_mrk_traces(data[ky]["marker"])
            ax.plot(
                offset(marker_ts, normalize(target_x)),
                drawstyle="steps-post",
                ls="--",
                label="Target_X",
                color="black",
            )

            for tx in trig_ts:
                ax.axvline(tx)
            # ax.plot(marker_ts, target_y, drawstyle='steps-post', ls='--', label='Target_Y', color='')
        if ky == "Mic":
            # read audio data
            audio_tstmp = data[ky]["device_data"]["time_stamps"]
            audio_ts = data[ky]["device_data"]["time_series"]
            chunk_len = audio_ts.shape[1]

            if chunk_len % 2:
                chunk_len -= 1
                time_mic = [t[0] for t in audio_ts]
                audio_ts = audio_ts[:, 1:]
                ax.plot(
                    offset(audio_tstmp), normalize(time_mic), "y--", label="audio clock"
                )

            # restructure audio data
            audio_tstmp = np.insert(
                audio_tstmp, 0, audio_tstmp[0] - np.diff(audio_tstmp).mean()
            )
            tstmps = []
            for i in range(audio_ts.shape[0]):
                tstmps.append(np.linspace(audio_tstmp[i], audio_tstmp[i + 1], chunk_len))
            audio_tstmp_full = np.hstack(tstmps)
            audio_ts_full = np.hstack(audio_ts)

            # plot audio data
            ax.plot(
                offset(audio_tstmp_full),
                normalize(audio_ts_full),
                label="Amplitude",
                alpha=0.5,
            )
        # if  any([ky in k for k in ["Intel_D455_2", 'IPhone', 'Flir']]):
        # if  any([ky in k for k in ["Intel_D455_2", 'IPhone']]):

        #  ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 0]-np.nanmean(data[ky]['device_data']['time_series'][:, 0])+20)*50, color='red', label=ky+'_red')
        # ax.plot(offset(data[ky]['device_data']['time_stamps']), normalize(data[ky]['device_data']['time_series'][:, 0]), color='blue', label=ky+'_blue')
        # ax.plot(offset(data[ky]['device_data']['time_stamps']), normalize(data[ky]['device_data']['time_series'][:, 1]), color='green', label=ky+'_green')
        # ax.plot(offset(data[ky]['device_data']['time_stamps']), normalize(data[ky]['device_data']['time_series'][:, 2]), color='red', label=ky+'_red')
        # ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 2]-np.nanmean(data[ky]['device_data']['time_series'][:, 2])+20)*50, color='blue', label=ky+'_blue')
        if "Intel_D455_3" in ky:
            #     ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 0]-np.nanmean(data[ky]['device_data']['time_series'][:, 0])+50)*20, color='darkred',  label=ky+'_red')
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, 2]),
                color="lightblue",
                label=ky + "_blue",
            )
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, 1]),
                color="lightgreen",
                label=ky + "_green",
            )
        #     ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 2]-np.nanmean(data[ky]['device_data']['time_series'][:, 2])+50)*20, color='darkblue', label=ky+'_blue')

        if "Intel_D455_1" in ky:
            #     ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 0]-np.nanmean(data[ky]['device_data']['time_series'][:, 0])+50)*20, color='darkred',  label=ky+'_red')
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, 2]),
                color="darkblue",
                label=ky + "_blue",
            )
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, 1]),
                color="darkgreen",
                label=ky + "_green",
            )
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, 0]),
                color="darkred",
                label=ky + "_red",
            )
        #     ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 2]-np.nanmean(data[ky]['device_data']['time_series'][:, 2])+50)*20, color='darkblue', label=ky+'_blue')

        if "FLIR" in ky:
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, 2]),
                ls="--",
                color="darkblue",
                label=ky + "_blue",
            )
            ax.plot(
                offset(data[ky]["device_data"]["time_stamps"]),
                normalize(data[ky]["device_data"]["time_series"][:, 1]),
                ls="--",
                color="darkgreen",
                label=ky + "_green",
            )
            # ax.plot(data[ky]['device_data']['time_stamps'], (data[ky]['device_data']['time_series'][:, 2]-np.nanmean(data[ky]['device_data']['time_series'][:, 2])+50)*20, ls='--',  color='darkblue', label=ky+'_blue')


    ax.legend(bbox_to_anchor=(1.0, 1), loc="upper left")
    plt.show()
