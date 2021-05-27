# -*- coding: utf-8 -*-
"""
Created on Thu Jan 14 08:21:16 2021

@author: adona
"""


paths = {}
paths["data_out"] = r"C:\neurobooth\neurobooth_data\\"
paths["LabRecorder"] = r'C:\neurobooth\LabRecorder\LabRecorder.exe'



task_config = {}

task_config["sync_test"]={
    "stimuli": "synch_task.html",
    "devices" : [
        "cameras",
        "micro",
        "mouse"
        ]    
    }

task_config["dsc"]={
    "stimuli": "DSC_simplified_oneProbe_2020.html",
    "devices" : [
        "cameras",
        "micro",
        ]    
    }

task_config["mt"]={
    "stimuli": "mouse_tracking.html",
    "devices" : [
        "cameras",
        "micro",
        "mouse"
        ]    
    }

task_config["ft"]={
    "stimuli": "task_motor_assess/motortask_instructions.html",
    "devices" : [
        "cameras",
        "micro",
        ]    
    }

mbient_macs = {
    "RH": "D1:49:43:61:54:08",
    "LH": "E7:81:46:1A:34:65",
    "LF": "CC:22:B5:89:7D:78"}

cam_inx = {
    "lowFeed": 1,
    "brio1": 0,
    "brio2": 8,
    "intel1": [1, '037522250727'],
    "intel2": [2, '036322250240'],
    "intel3": [3, '037322251461']    
    }