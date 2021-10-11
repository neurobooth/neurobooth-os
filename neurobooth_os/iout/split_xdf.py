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


def split_sens_files(fname, tech_obs_log_id=None):
    """Split xdf file per sensor

    Parameters
    ----------
    fname : str
        name of the file to split
    tech_obs_log_id : str, optional
        task id for the database, by default None

    Returns
    -------
    files : list
        list of files for each stream
    """

    # Read xdf file
    data, header = pyxdf.load_xdf(fname)

    # Find marker stream to add in to each h5 file
    marker = [d for d in data if d['info']['name'] == ["Marker"]]

    if tech_obs_log_id is not None:
        conn = meta.get_conn()
        table_sens_log = Table("sensor_file_log", conn=conn)

    files = []
    # Loop over each sensor
    for dev_data in data:
        name = dev_data['info']['name'][0]
        if name == "Marker":
            continue

        device_id = dev_data['info']['desc'][0]["device_id"][0]
        sensors_id = eval(dev_data['info']['desc'][0]["sensor_ids"][0])

        sensors = "-".join(sensors_id)
        data_sens = [marker, dev_data]
        head, ext = op.splitext(fname)
        fname_full = f"{head}_{device_id}_{sensors}.hdf5"
        write_hdf5(fname_full, data_sens, overwrite=True)
        print(f"Saving stream {name} to {fname_full}")
        files.append(fname_full)
        _, head = op.split(fname_full)

        time_offset = compute_clocks_diff()
        start_time = dev_data['time_stamps'][0] + time_offset
        end_time = dev_data['time_stamps'][-1] + time_offset
        start_time = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
        end_time = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")
        temp_res = 1 / np.median(np.diff(dev_data['time_stamps']))

        if "intel" in name.lower():
            fname_bag = dev_data['info']['desc'][0]["filename"][0]
            head = f",{head}, {fname_bag}"
            print(head)

        if tech_obs_log_id is not None:
            for sens_id in sensors_id:
                cols = ["tech_obs_log_id", "true_temporal_resolution", "true_spatial_resolution",
                 "file_start_time", "file_end_time", "device_id", "sensor_id", 'sensor_file_path']
                vals = [(tech_obs_log_id, temp_res, None, start_time, end_time, device_id, sens_id,
                 "{" + head + "}")]
                table_sens_log.insert_rows(vals, cols)

    return files

def get_xdf_name(session, fname_prefix):
    
    fname = session.folder / Path(fname_prefix + ".xdf")
    base_stem = fname.stem.split("_R")[0]
    count = 0
    for f in fname.parent.glob(fname.stem + "*.xdf"):
        base_stem, run_counter = f.stem.split("_R")
        count = max(int(run_counter), count)
    run_str = "_R{0:03d}".format(count)
    final_fname = str(fname.with_name(base_stem + run_str).with_suffix(".xdf"))
    return final_fname