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
from h5io import write_hdf5
from neurobooth_os.iout import metadator as meta
from neurobooth_terra import Table

conn = meta.get_conn()
table_sens_log = Table("sensor_file_log", conn=conn)


def compute_clocks_diff():
    """Compute difference between local LSL and Unix clock
    Args:
        None
    Returns:
        time_offset (float): Offset between the clocks
    """
    time_local = pylsl.local_clock()
    time_ux = time.time()
    time_offset = time_ux - time_local
    return time_offset


def split(fname, tech_obs_log_id):
    """Split xdf file per sensor
    Args:
        fname (str): The xdf filename to load
        fname (str): The xdf filename to load
    Returns:
        None
    """

    # Read xdf file
    data, header = pyxdf.load_xdf(fname)

    # Find marker stream to add in to each h5 file
    marker = [d for d in data if d['info']['name'] == ["Marker"]]

    # Loop over each sensor
    for dev_data in data:
        name = dev_data['info']['name']
        if name == "Marker":
            continue

        device_id = dev_data['info']['desc'][0]["device_id"][0]
        sensors_id = eval(dev_data['info']['desc'][0]["sensor_ids"][0])

        sensors = "-".join(sensors_id)
        data_sens = [marker, dev_data]
        head, ext = op.splitext(fname)
        fname_full = f"{head}_{device_id}_{sensors}.hdf5"
        write_hdf5(fname_full, data_sens, overwrite=True)
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

        for sens_id in sensors_id:
            vals = [(tech_obs_log_id, temp_res, None, None, start_time, end_time, device_id, sens_id, "{" + head + "}")]
            cols = ["tech_obs_log_id", "true_temporal_resolution", "true_spatial_resolution", "file_start_time",
                    "file_end_time", "device_id", "sensor_id", 'sensor_file_path']
            table_sens_log.insert_rows(vals, cols)
