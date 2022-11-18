# -*- coding: utf-8 -*-
"""
Created on Fri Apr 29 13:54:38 2022

@author: ACQ
"""


# usage: python data_fuser.py [mac1] [mac2] ... [mac(n)]
from __future__ import print_function
from ctypes import c_void_p, cast, POINTER
from mbientlab.metawear import MetaWear, libmetawear, parse_value, cbindings
from time import sleep
from threading import Event
from sys import argv
from pylsl import local_clock
import numpy as np

states = []

global dt


class State:
    # init
    def __init__(self, device):
        self.device = device
        self.callback = cbindings.FnVoid_VoidP_DataP(self.data_handler)
        self.processor = None
        self.dt = []

    # download data callback fxn
    def data_handler(self, ctx, data):
        values = parse_value(data, n_elem=1)
        self.data = data
        self.dt.append(local_clock())
        # print("acc: (%.4f,%.4f,%.4f), gyro; (%.4f,%.4f,%.4f)" % (values[0].x, values[0].y, values[0].z, values[1].x, values[1].y, values[1].z))

    # setup
    def setup(self):
        # ble settings
        libmetawear.mbl_mw_settings_set_connection_parameters(
            self.device.board, 7.5, 7.5, 0, 6000
        )
        sleep(1.5)

        # setup acc
        libmetawear.mbl_mw_acc_set_odr(self.device.board, 100.0)
        libmetawear.mbl_mw_acc_set_range(self.device.board, 16.0)
        libmetawear.mbl_mw_acc_write_acceleration_config(self.device.board)
        # get acc and subscribe
        signal = libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.device.board)
        libmetawear.mbl_mw_datasignal_subscribe(signal, None, self.callback)

    # start
    def start(self):
        # start acc sampling
        libmetawear.mbl_mw_acc_enable_acceleration_sampling(self.device.board)

        # start acc
        libmetawear.mbl_mw_acc_start(self.device.board)


# connect
mbients = {
    "LF": "DA:B0:96:E4:7F:A3",
    "LH": "E8:95:D6:F7:39:D2",
    "RF": "E5:F6:FB:6D:11:8A",
    "RH": "FE:07:3E:37:F5:9C",
    "BK": "D7:B0:7E:C2:A1:23",
}


macs = ["E5:F6:FB:6D:11:8A"]
macs = [mbients["LH"], mbients["RF"], mbients["RH"]]
for i in range(len(macs)):
    d = MetaWear(macs[i])
    d.connect()
    print(
        "Connected to "
        + d.address
        + " over "
        + ("USB" if d.usb.is_connected else "BLE")
    )
    states.append(State(d))

# configure
for s in states:
    print("Configuring %s" % (s.device.address))
    s.setup()

# start
for s in states:
    s.start()

# wait 10 s
sleep(100.0)

# reset
print("Resetting devices")
events = []
for s in states:
    e = Event()
    events.append(e)

    s.device.on_disconnect = lambda s: e.set()
    libmetawear.mbl_mw_debug_reset(s.device.board)
    print(
        f"num samples:{len(s.dt)}, Fps median:{int(np.median(1/np.diff(s.dt)))}, mean:{int(np.mean(1/np.diff(s.dt)))}"
    )

for e in events:
    e.wait()

# import matplotlib.pyplot as plt
# fig, axs = plt.subplots(2, len(states))
# for ix, s in enumerate(states):

#     axs[0,ix].plot(np.diff(s.dt))
#     axs[1, ix].hist(np.diff(s.dt))
