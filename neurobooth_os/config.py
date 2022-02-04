# -*- coding: utf-8 -*-
"""
Created on Thu Jan 14 08:21:16 2021

@author: adona
"""
import os.path as op
from os.path import expanduser
import json

# if files does not exist create it in user root dir
fname = op.join(expanduser("~"), ".neurobooth_os_config")
if not op.exists(fname):        
    paths = {
        "data_out": r"C:\neurobooth\neurobooth_data\\",
        'nas': r'Z:\data\\',
        'video_tasks' : r"C:\Users\STM\Dropbox (Partners HealthCare)\Neurobooth Videos for tasks\Videos_to_present",
        'cam_inx_lowfeed' : 0
        }
    with open(fname, "w+") as f:
        json.dump(paths, f, ensure_ascii=False, indent=4)

with open(fname, 'r') as f:
    paths = json.load(f)

