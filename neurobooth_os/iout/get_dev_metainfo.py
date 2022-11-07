# -*- coding: utf-8 -*-
"""
Created on Wed Jul 14 11:24:43 2021

@author: ACQ
"""
import socket
from collections import OrderedDict

import pyrealsense2 as rs
import PySpin
import pyaudio

import psycopg2
from neurobooth_terra import Table

import neurobooth_os.config as cfg
from neurobooth_os.iout.mbient import Sensor
from neurobooth_os.iout.metadator import get_conn

############# INSERT ROWS IN DATABASE #############


def insert_to_table(table_id, row_dicts):
    """Insert to table.

    Parameters
    ----------
    table_id : str
        The table ID
    row_dicts : list of dict
        The rows to insert
    """

    conn = get_conn()

    table = Table(table_id, conn=conn)
    cols = table.column_names
    vals = list()
    for row_dict in row_dicts:
        vals.append(tuple(row_dict.get(col, None) for col in cols))

    table.insert_rows(vals, cols)


def make_id_array(dictionary):
    # make string from dict keys for id_array keys
    return "{" + ", ".join([k for k in dictionary.keys()]) + "}"


############# SENSORS #############


sens_info_dict = {
    "sensor_id": "",  # VARCHAR(255) NOT NULL,
    "temporal_res": "",  # FLOAT NOT NULL,
    "spatial_res_x": "",  # FLOAT NOT NULL,
    "spatial_res_y": "",
    "file_type": "",
}

sens_intel = OrderedDict()
sens_intel["Intel_D455_rgb_1"] = {
    "sensor_id": "Intel_D455_rgb_1",  # VARCHAR(255) NOT NULL,
    "temporal_res": 60,  # FLOAT NOT NULL,
    "spatial_res_x": 640,  # FLOAT NOT NULL,
    "spatial_res_y": 480,
    "file_type": "bag",
}
sens_intel["Intel_D455_depth_1"] = {
    "sensor_id": "Intel_D455_depth_1",  # VARCHAR(255) NOT NULL,
    "temporal_res": 60,  # FLOAT NOT NULL,
    "spatial_res_x": 640,  # FLOAT NOT NULL,
    "spatial_res_y": 480,
    "file_type": "bag",
}

sens_mbient = OrderedDict()
sens_mbient["mbient_acc_1"] = {
    "sensor_id": "mbient_acc_1",  # VARCHAR(255) NOT NULL,
    "temporal_res": 200,  # FLOAT NOT NULL,
    "file_type": "xdf",
}
sens_mbient["mbient_gra_1"] = {
    "sensor_id": "mbient_gra_1",  # VARCHAR(255) NOT NULL,
    "temporal_res": 200,  # FLOAT NOT NULL,
    "file_type": "xdf",
}

sens_FLIR = OrderedDict()
sens_FLIR["FLIR_rgb_1"] = {
    "sensor_id": "FLIR_rgb_1",  # VARCHAR(255) NOT NULL,
    "temporal_res": 196,  # FLOAT NOT NULL,
    "spatial_res_x": "1600",  # FLOAT NOT NULL,
    "spatial_res_y": "1100",
    "file_type": "mp4",
}


sens_yeti = OrderedDict()
sens_yeti["Yeti_mic_1"] = {
    "sensor_id": "Yeti_mic_1",  # VARCHAR(255) NOT NULL,
    "temporal_res": 44100,  # FLOAT NOT NULL,
    "spatial_res_x": 1024,  # FLOAT NOT NULL,
    "spatial_res_y": None,
    "file_type": "xdf",
}

insert_to_table("nb_sensor", list(sens_yeti.values()))

for sens in [sens_intel, sens_mbient, sens_FLIR]:
    insert_to_table("nb_sensor", list(sens.values()))

# eyelink

sens_Eyelink = OrderedDict()
sens_Eyelink["Eyelink_sens_1"] = {
    "sensor_id": "Eyelink_sens_1",  # VARCHAR(255) NOT NULL,
    "temporal_res": 1000,  # FLOAT NOT NULL,
    "spatial_res_x": None,  # FLOAT NOT NULL,
    "spatial_res_y": None,
    "file_type": "edf",
}
insert_to_table("nb_sensor", list(sens_Eyelink.values()))

############# DEVICES #############

dev_info_dict = {
    "device_id": "",
    "device_sn": "",
    "wearable_bool": False,
    "device_location": "0_0_0",
    "device_name": "",
    "device_model": "",
    "device_make": "",
    "device_firmware": "",
    "sensor_id_array": "{}",
}


# Intel

dev_intels = []

for intel in ["intel1", "intel2", "intel3"]:
    config = rs.config()
    config.enable_device(cfg.cam_inx[intel][1])
    pipeline = rs.pipeline()
    profile = config.resolve(pipeline)
    device = profile.get_device()

    dev_intel_info = {
        "device_id": "Intel_D455_" + intel[-1],
        "device_sn": device.get_info(rs.camera_info.serial_number),
        "wearable_bool": False,
        "device_location": "0_0_0",
        "device_name": device.get_info(rs.camera_info.name),
        "device_model": device.get_info(rs.camera_info.name).split(" ")[-1],
        "device_make": device.get_info(rs.camera_info.name)[:-5],
        "device_firmware": device.get_info(rs.camera_info.firmware_version),
        "sensor_id_array": make_id_array(sens_intel),
    }
    dev_intels.append(dev_intel_info)

insert_to_table("nb_device", dev_intels)


# Mbient
dev_mbient = []
for k, mac in cfg.mbient_macs.items():
    try:
        mbt = Sensor(mac)
        mbient_info = mbt.device.info
        mbient_info["address"] = mbt.device.address
        mbient_info["device_name"] = mbt.dev_name
        mbt.close()

        dev_mbient_dict = {
            "device_id": f"Mbient_{k}_1",
            "device_sn": mbient_info["address"],
            "wearable_bool": True,
            "device_location": "Null",
            "device_name": mbient_info["device_name"],
            "device_model": mbient_info["model"],
            "device_make": mbient_info["manufacturer"],
            "device_firmware": mbient_info["firmware"],
            "sensor_id_array": make_id_array(sens_mbient),
        }
        dev_mbient.append(dev_mbient_dict)
    except BaseException:
        continue

insert_to_table("nb_device", dev_mbient)

# FLIR camera
system = PySpin.System.GetInstance()
cam = system.GetCameras()[0]
dev_FLIR_info = {
    "device_id": "FLIR_blackfly_1",
    "device_sn": cam.TLDevice.DeviceSerialNumber.GetValue(),
    "wearable_bool": False,
    "device_location": "50_50_180",
    "device_name": cam.TLDevice.DeviceDisplayName(),
    "device_model": cam.TLDevice.DeviceModelName.GetValue(),
    "device_make": cam.TLDevice.DeviceVendorName.GetValue(),
    "device_firmware": cam.TLDevice.DeviceVersion.GetValue(),
    "sensor_id_array": make_id_array(sens_FLIR),
}

insert_to_table("nb_device", [dev_FLIR_info])

# Yeti mic
audio = pyaudio.PyAudio()

# Get Blue Yeti mic device ID
info = audio.get_host_api_info_by_index(0)
for i in range(info.get("deviceCount")):
    if (
        audio.get_device_info_by_host_api_device_index(0, i).get("maxInputChannels")
    ) > 0:
        dev_info = audio.get_device_info_by_host_api_device_index(0, i)

        if "BLUE USB" in dev_info["name"]:
            dev_inx = i
            device_name = dev_info["name"]
            break

dev_Yeti_info = {
    "device_id": "Yeti_mic_dev_1",
    "device_sn": "None",
    "wearable_bool": False,
    "device_location": "44_42_56",
    "device_name": device_name,
    "device_model": "Yeti Pro",
    "device_make": "BLUE Yeti",
    "device_firmware": "None",
    "sensor_id_array": make_id_array(sens_yeti),
}

insert_to_table("nb_device", [dev_Yeti_info])

pc_name = socket.gethostname()

if pc_name == "stm":
    import pylink

    ip = "192.168.100.15"

    tk = pylink.EyeLink(ip)

    dev_Eyelink_info = {
        "device_id": "Eyelink_1",
        "device_sn": tk.getTrackerAddress(),
        "wearable_bool": False,
        "device_location": "25_19_36",
        "device_name": "EYELIN Portable Duo",
        "device_model": tk.getTrackerVersionString(),
        "device_make": "SR",
        "device_firmware": "None",
        "sensor_id_array": make_id_array(sens_Eyelink),
    }

    insert_to_table("nb_device", [dev_Eyelink_info])
