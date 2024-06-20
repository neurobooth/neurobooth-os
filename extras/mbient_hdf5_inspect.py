# -*- coding: utf-8 -*-
"""
Created on Tue May  3 15:35:18 2022

@author: ACQ
"""

import glob
from h5io import read_hdf5
import os.path as op
import numpy as np

lsl_session = "100089_2022-06-01"
lsl_session = "100064_2022-06-03"
files = glob.glob(f"Z:/data/{lsl_session}/{lsl_session}*Mbient*.hdf5")

for fl in files:
    data = read_hdf5(fl)

    fps = data["device_data"]["time_stamps"]

    _, name = op.split(fl)
    print(
        name.replace(lsl_session, "").replace("-mbient_acc_1-mbient_gyro_1.hdf5", ""),
        len(fps),
        1 / np.mean(np.diff(fps)),
    )
