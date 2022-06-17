# -*- coding: utf-8 -*-
"""
Created on Mon May  9 13:08:47 2022

@author: STM
"""

import pyxdf
import glob
import os.path as op

fname = 'Z:/data/100090_2022-05-09/100090_2022-05-09_11h-49m-48s_saccades_vertical_obs_1_R001.xdf'

session = "100114_2022-06-02"
fnames = glob.glob(f'Z:/data/{session}/{session}_*.xdf')

for fname in fnames:
    data, header = pyxdf.load_xdf(fname)
    _, file = op.split(fname)
    print(file)
    for d in data:
        # if "mbient" in d['info']['name'][0]:
             
            length = d["time_stamps"][-1] - d["time_stamps"][0]
            fps = len( d["time_stamps"])/length
            print(d['info']['name'][0], d['info']['hostname'][0], length, fps)
            