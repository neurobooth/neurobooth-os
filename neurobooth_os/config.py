# -*- coding: utf-8 -*-
"""
Created on Thu Jan 14 08:21:16 2021

@author: adona
"""


paths = {}
paths["data_out"] = r"C:\neurobooth\neurobooth_data\\"
paths["LabRecorder"] = r'C:\neurobooth\LabRecorder\LabRecorder.exe'
paths['nas'] =  r'Z:\session_data\\'


mbient_macs = {
    "RH": "EE:99:D8:9D:69:5F",  #"D1:49:43:61:54:08",
    "LH": "CE:F3:BD:BD:04:8F",
    "LF": "CC:22:B5:89:7D:78"}

cam_inx = {
    "lowFeed": 0,
    # "brio1": 4,
    # "brio2": 7,
    "intel1": [1, '037522250727'],
    "intel2": [2, '036322250240'],
    "intel3": [3, '037322251461']    
    }