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
        self.dt =[]
    # download data callback fxn
    def data_handler(self, ctx, data):
        values = parse_value(data, n_elem = 2)
        self.dt.append(local_clock())
        # print("acc: (%.4f,%.4f,%.4f), gyro; (%.4f,%.4f,%.4f)" % (values[0].x, values[0].y, values[0].z, values[1].x, values[1].y, values[1].z))
    # setup
    def setup(self):
        # ble settings
        libmetawear.mbl_mw_settings_set_connection_parameters(self.device.board, 7.5, 7.5, 0, 6000)
        sleep(1.5)
        
        libmetawear.mbl_mw_acc_set_odr(self.device.board, 100)
        libmetawear.mbl_mw_acc_set_range(self.device.board, 16.0)
        libmetawear.mbl_mw_acc_write_acceleration_config(self.device.board)
        
        # libmetawear.mbl_mw_gyro_bmi160_set_odr(self.device.board, 100)        
        # libmetawear.mbl_mw_gyro_bmi160_set_range(self.device.board, 2000)
        # libmetawear.mbl_mw_gyro_bmi160_write_config(self.device.board)
        
        # events
        e = Event()
        # processor callback fxn
        def processor_created(context, pointer):
            self.processor = pointer
            e.set()
        # processor fxn ptr
        fn_wrapper = cbindings.FnVoid_VoidP_VoidP(processor_created)
        # get acc signal
        acc = libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.device.board)
        # get gyro signal - MMRl, MMR, MMc ONLY
        #gyro = libmetawear.mbl_mw_gyro_bmi160_get_rotation_data_signal(self.device.board)
        # get gyro signal - MMRS ONLY
        gyro = libmetawear.mbl_mw_gyro_bmi270_get_rotation_data_signal(self.device.board)
        # create signals variable
        signals = (c_void_p * 1)()
        signals[0] = gyro
        # create acc + gyro signal fuser
        libmetawear.mbl_mw_dataprocessor_fuser_create(acc, signals, 1, None, fn_wrapper)
        # wait for fuser to be created
        e.wait()
        # subscribe to the fused signal
        libmetawear.mbl_mw_datasignal_subscribe(self.processor, None, self.callback)
    # start
    def start(self):
        # start gyro sampling - MMRL, MMC, MMR only
        #libmetawear.mbl_mw_gyro_bmi160_enable_rotation_sampling(self.device.board)
        # start gyro sampling - MMS ONLY
        libmetawear.mbl_mw_gyro_bmi270_enable_rotation_sampling(self.device.board)
        # start acc sampling
        libmetawear.mbl_mw_acc_enable_acceleration_sampling(self.device.board)
        # start gyro - MMRL, MMC, MMR only
        #libmetawear.mbl_mw_gyro_bmi160_start(self.device.board)
        # start gyro sampling - MMS ONLY
        libmetawear.mbl_mw_gyro_bmi270_start(self.device.board)
        # start acc
        libmetawear.mbl_mw_acc_start(self.device.board)
        
# connect
mbients = {"LF": "DA:B0:96:E4:7F:A3",
           "LH": "E8:95:D6:F7:39:D2",
           "RF": "E5:F6:FB:6D:11:8A",
           "RH": "FE:07:3E:37:F5:9C",
           "BK": "D7:B0:7E:C2:A1:23"
           }


macs = ["E5:F6:FB:6D:11:8A"]  
macs =  [  mbients['LH'], mbients["RF"],  mbients["RH"]]
for i in range(len(macs) ):
    d = MetaWear(macs[i])
    d.connect()
    print("Connected to " + d.address + " over " + ("USB" if d.usb.is_connected else "BLE"))
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
    

for e in events:
    e.wait()

for s in states:
    print(f"num samples:{len(s.dt)}, Fps median:{int(np.median(1/np.diff(s.dt)))}, mean:{int(np.mean(1/np.diff(s.dt)))}")