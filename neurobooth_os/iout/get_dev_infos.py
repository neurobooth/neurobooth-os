# -*- coding: utf-8 -*-
"""
Created on Wed Jul 14 11:24:43 2021

@author: ACQ
"""

from neurobooth_os.iout.mbient import Sensor
import pyrealsense2 as rs

import PySpin

# Intel
ctx = rs.context()
devices = ctx.query_devices()
print (devices[0])
device = devices[1]


intel_info = {
    "name" : device.get_info(rs.camera_info.name),
    "firmware": device.get_info(rs.camera_info.firmware_version),
    "sn" : device.get_info(rs.camera_info.serial_number),
    "usb_port" : device.get_info(rs.camera_info.physical_port),
    "usb_type" : device.get_info(rs.camera_info.usb_type_descriptor)}


# Mbient
mac = "EE:99:D8:9D:69:5F"
mbt = Sensor(mac)
mbient_info = mbt.device.info
mbient_info["address"] = mbt.device.address
mbt.close()

# FLIR camera
system = PySpin.System.GetInstance()
cam = system.GetCameras()[0]

# sn = cam.TLDevice.DeviceSerialNumber.GetValue()
# cam.TLDevice.DeviceDisplayName()
# cam.TLDevice.DeviceDriverVersion.GetValue()
# "usb_port" :cam.TLDevice.DeviceID.GetValue()
# cam.TLDevice.DeviceLocation.GetValue()
# cam.TLDevice.DeviceModelName.GetValue()
# cam.TLDevice.DeviceVersion.GetValue()
# cam.TLDevice.DeviceType.GetValue()
# cam.TLDevice.DeviceVendorName.GetValue()

nodemap = cam.GetTLDeviceNodeMap()
node_device_information = PySpin.CCategoryPtr(nodemap.GetNode("DeviceInformation"))
features = node_device_information.GetFeatures()
for feature in features:
    node_feature = PySpin.CValuePtr(feature)
    print ("%s: %s" % (node_feature.GetName(),
                      node_feature.ToString() if PySpin.IsReadable(node_feature) else "Node not readable"))
