# -*- coding: utf-8 -*-
"""
Created on Thu Jan 14 08:21:16 2021

@author: adona
"""


paths = {}
paths["data_out"] = r"C:\Users\neurobooth\Desktop\neurobooth\neurobooth_data\\"
paths["LabRecorder"] = r'C:\Users\neurobooth\Desktop\neurobooth\software\LabRecorder\LabRecorder.exe'



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