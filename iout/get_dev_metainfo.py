# -*- coding: utf-8 -*-
"""
Created on Wed Jul 14 11:24:43 2021

@author: ACQ
"""

from iout.mbient import Sensor
import pyrealsense2 as rs
from collections import OrderedDict
import PySpin


# Intel
ctx = rs.context()
devices = ctx.query_devices()
print (devices[0])
device = devices[1]

# Mbient
mac = "EE:99:D8:9D:69:5F"
mbt = Sensor(mac)
mbient_info = mbt.device.info
mbient_info["address"] = mbt.device.address
mbient_info["device_name"]= mbt.dev_name
mbt.close()


# FLIR camera
system = PySpin.System.GetInstance()
cam = system.GetCameras()[0]

############# SENSORS #############

sens_info_dict = {
    "sensor_id" :  "",#VARCHAR(255) NOT NULL,
    "temporal_res" :"" ,#FLOAT NOT NULL,
    "spatial_res_x" : "", #FLOAT NOT NULL,
    "spatial_res_y" : "",
    "file_type" : "",
    }
    
sens_intel = OrderedDict()
sens_intel["sens_Intel_D455_rgb_0"] =   {
        "sensor_id" : "Intel_D455_rgb_0",#VARCHAR(255) NOT NULL,
        "temporal_res" : 60,#FLOAT NOT NULL,
        "spatial_res_x" : 640, #FLOAT NOT NULL,
        "spatial_res_y" : 480,
        "file_type" : "bag"
        }
sens_intel["sens_Intel_D455_depth_0"] =  {
        "sensor_id" : "Intel_D455_depth_0",#VARCHAR(255) NOT NULL,
        "temporal_res" : 60,#FLOAT NOT NULL,
        "spatial_res_x" : 640, #FLOAT NOT NULL,
        "spatial_res_y" : 480,
        "file_type" : "bag"
        }

sens_mbient = OrderedDict()
sens_mbient["mbient_acc_0"] =   {
        "sensor_id" : "mbient_acc_0",#VARCHAR(255) NOT NULL,
        "temporal_res" : 200,#FLOAT NOT NULL,
        "spatial_res_x" : "NULL", #FLOAT NOT NULL,
        "spatial_res_y" : "NULL",
        "file_type" : "xdf"
        }
sens_mbient["mbient_gra_0"] =  {
        "sensor_id" : "mbient_gra_0",#VARCHAR(255) NOT NULL,
        "temporal_res" : 200,#FLOAT NOT NULL,
        "spatial_res_x" : "NULL", #FLOAT NOT NULL,
        "spatial_res_y" : "NULL",
        "file_type" : "xdf"
        }

sens_FLIR = OrderedDict()
sens_FLIR["FLIR_rgb_0"] =   {
        "sensor_id" : "FLIR_rgb_0",#VARCHAR(255) NOT NULL,
        "temporal_res" : 196,#FLOAT NOT NULL,
        "spatial_res_x" : "1600", #FLOAT NOT NULL,
        "spatial_res_y" : "1100",
        "file_type" : "mp4"
        }

############# DEVICES #############

def make_id_array(dictionary):
    # make string from dict keys for id_array keys
    return "{"+", ".join([k for k in dictionary.keys()])+"}"


dev_info_dict = {
    "device_id" : "",
    "device_sn" : "",
    "wearable_bool" : False,
    "device_location" : "0_0_0",
    "device_name" : "",
    "device_model" : "",
    'device_make' :"",
    'device_firmware' : "",
    "sensor_id_array": "{}"
    }

dev_intel_info = {
    "device_id" : "Intel_D455_0",
    "device_sn" : device.get_info(rs.camera_info.serial_number),
    "wearable_bool" : False,
    "device_location" : "0_0_0",
    "device_name" : device.get_info(rs.camera_info.name),
    "device_model" : device.get_info(rs.camera_info.name).split(" ")[-1],
    'device_make' : device.get_info(rs.camera_info.name)[:-5],
    "device_firmware": device.get_info(rs.camera_info.firmware_version),
    "sensor_id_array": make_id_array(sens_intel),
    }

dev_mbient_dict = {
    "device_id" : "Mbient_LH",
    "device_sn" : mbient_info['address'], # MAC instead of SN
    "wearable_bool" : True,
    "device_location" : "Null",
    "device_name" : mbient_info["device_name"],
    "device_model" : mbient_info["model"],
    'device_make' : mbient_info["manufacturer"],
    'device_firmware' : mbient_info["firmware"],
    "sensor_id_array":  make_id_array(sens_mbient)
    }

dev_FLIR_info = {
    "device_id" : "FLIR_blackfly_0",
    "device_sn" : cam.TLDevice.DeviceSerialNumber.GetValue(),
    "wearable_bool" : False,
    "device_location" : "50_50_180",
    "device_name" : cam.TLDevice.DeviceDisplayName(),
    "device_model" : cam.TLDevice.DeviceModelName.GetValue(),
    'device_make' : cam.TLDevice.DeviceVendorName.GetValue(),
    'device_firmware' : cam.TLDevice.DeviceVersion.GetValue(),
    "sensor_id_array": make_id_array(sens_FLIR)
    }



