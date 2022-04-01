# -*- coding: utf-8 -*-
# Authors: Sheraz Khan <sheraz@khansheraz.com>
#
# License: BSD-3-Clause
# Split xdf file per sensor


import pyxdf
import pylsl
import time
import numpy as np
import os.path as op
from datetime import datetime
from pathlib import Path

from h5io import write_hdf5

from neurobooth_os.iout import metadator as meta
from neurobooth_terra import Table


def compute_clocks_diff():
    """Compute difference between local LSL and Unix clock

    Returns
    -------
    time_offset : float
        time_offset (float): Offset between the clocks
    """

    time_local = pylsl.local_clock()
    time_ux = time.time()
    time_offset = time_ux - time_local
    return time_offset


def split_sens_files(fname, log_task_id=None, tech_obs_id=None, conn=None, folder=''):
    """Split xdf file per sensor

    Parameters
    ----------
    fname : str
        name of the file to split
    log_task_id : str, optional
        task log id for the database, by default None. If conn not None, it can not be None. 
    tech_obs_id : str, optional
        task id for the database, by default None. If conn not None, it can not be None. 
    conn : callable
        Connector to the database, if None does not insert rows, by default None
    folder : str
        path to fname

    Returns
    -------
    files : list
        list of files for each stream
    """

    # Read xdf file
    data, header = pyxdf.load_xdf(fname)

    # Find marker stream to add in to each h5 file
    marker = [d for d in data if d['info']['name'] == ["Marker"]]

    if conn is not None:
        table_sens_log = Table("log_sensor_file", conn=conn)
        _, devices_ids, _, _ = meta._get_task_param(tech_obs_id, conn)
    # get video filenames if videofiles marker present
    videofiles = {}
    if 'videofiles' in [d['info']['name'][0] for d in data]:
        vid_data = [v for v in data if v['info']['name'] == ['videofiles']]
        # video file marker format is ["streamName, fname.mov"]
        videofiles = {d[0].split(",")[0] : d[0].split(",")[1] for d in vid_data[0]['time_series'] 
                        if d[0]!= ''}

    files = []
    # Loop over each sensor
    for dev_data in data:
        name = dev_data['info']['name'][0]
        if name in ["Marker", "videofiles"]:
            continue

        device_id = dev_data['info']['desc'][0]["device_id"][0]
        sensors_id = eval(dev_data['info']['desc'][0]["sensor_ids"][0])

        # Only log and split devices in tech_obs DB
        if tech_obs_id is not None and device_id not in devices_ids:
            # print(f"Skipping {name} not in tech obs device list: {devices_ids}")
            continue
        
        sensors = "-".join(sensors_id)
        data_sens = {'marker': marker[0], 'device_data': dev_data}
        head, ext = op.splitext(fname)
        fname_full = f"{head}-{device_id}-{sensors}.hdf5"
        write_hdf5(fname_full, data_sens, overwrite=True)
        # print(f"Saving stream {name} to {fname_full}")
        files.append(fname_full)
        _, head = op.split(fname_full)

        time_offset = compute_clocks_diff()
        start_time = dev_data['time_stamps'][0] + time_offset
        end_time = dev_data['time_stamps'][-1] + time_offset
        start_time = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
        end_time = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")
        temp_res = 1 / np.median(np.diff(dev_data['time_stamps']))

        if len(folder):
            head = f"{folder}/{head}"

        if videofiles.get(name): 
            if len(folder):
                head = f"{head}, {folder}/{videofiles.get(name)}"
            else:
                head = f"{head}, {videofiles.get(name)}"
            # print(f"Videofile name: {head}")
        
        if log_task_id is not None:
            for sens_id in sensors_id:
                cols = ["log_task_id", "true_temporal_resolution", "true_spatial_resolution",
                 "file_start_time", "file_end_time", "device_id", "sensor_id", 'sensor_file_path']
                vals = [(log_task_id, temp_res, None, start_time, end_time, device_id, sens_id,
                 "{" + head + "}")]
                table_sens_log.insert_rows(vals, cols)

    return files

def get_xdf_name(session, fname_prefix):
    """Get with most recent session xdf file name.

    Parameters
    ----------
    session : instance of liesl.Session
        Callable with session.folder path
    fname_prefix : str
        Prefix name of the xdf file name

    Returns
    -------
    final file name : str
        File name of the xdf file
    """
    fname = session.folder / Path(fname_prefix + ".xdf")
    base_stem = fname.stem.split("_R")[0]
    count = 0
    for f in fname.parent.glob(fname.stem + "*.xdf"):
        base_stem, run_counter = f.stem.split("_R")
        count = max(int(run_counter), count)
    run_str = "_R{0:03d}".format(count)
    final_fname = str(fname.with_name(base_stem + run_str).with_suffix(".xdf"))
    return final_fname