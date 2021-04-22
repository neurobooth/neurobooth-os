# usage: python data_fuser.py [mac1] [mac2] ... [mac(n)]
from __future__ import print_function
from ctypes import c_void_p, cast, POINTER
from mbientlab.metawear import MetaWear, libmetawear, parse_value, cbindings
from time import sleep
from threading import Event
from sys import argv
from pylsl import StreamInfo, StreamOutlet
import uuid


states = []

class Sensor:
    def __init__(self, mac_address, buzz_time_sec=2):
        
        self.mac = mac_address
        self.connector = MetaWear
        self.connect()
        
        self.processor = None
        self.buzz_time = buzz_time_sec *1000

        # Setup outlet stream infos
        self.stream_mbient = StreamInfo(name='mbient', type='acc',
                                        channel_count=6, channel_format='float32',
                                        source_id=str(uuid.uuid4()))      
        self.streaming = False        
        self.setup()
       
    def connect(self):        
        self.device = self.connector(self.mac)
        self.device.connect()       
        print(f"Mbient {self.mac} connected")
        
    def data_handler(self, ctx, data):
        values = parse_value(data, n_elem = 2)
        vals = [values[0].x, values[0].y, values[0].z, values[1].x, values[1].y, values[1].z]
        
        self.outlet.push_sample(vals)
        # print("acc: (%.4f,%.4f,%.4f), gyro; (%.4f,%.4f,%.4f)" % (values[0].x, values[0].y, values[0].z, values[1].x, values[1].y, values[1].z))


    def setup(self):
        libmetawear.mbl_mw_settings_set_connection_parameters(self.device.board, 7.5, 7.5, 0, 6000)
        sleep(1.5)

        e = Event()

        def processor_created(context, pointer):
            self.processor = pointer
            e.set()
        fn_wrapper = cbindings.FnVoid_VoidP_VoidP(processor_created)

        self.outlet = StreamOutlet(self.stream_mbient)
            
        self.callback = cbindings.FnVoid_VoidP_DataP(self.data_handler)

        acc = libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.device.board)
        gyro = libmetawear.mbl_mw_gyro_bmi160_get_rotation_data_signal(self.device.board)

        signals = (c_void_p * 1)()
        signals[0] = gyro
        libmetawear.mbl_mw_dataprocessor_fuser_create(acc, signals, 1, None, fn_wrapper)
        e.wait()

        libmetawear.mbl_mw_datasignal_subscribe(self.processor, None, self.callback)
        
        print(f"Mbient {self.mac} setup")
        
    def start(self):
        print(f"Started mbient {self.mac}")
        libmetawear.mbl_mw_gyro_bmi160_enable_rotation_sampling(self.device.board)
        libmetawear.mbl_mw_acc_enable_acceleration_sampling(self.device.board)
        
        # Vibrate for 7 secs and then start aqc
        libmetawear.mbl_mw_haptic_start_motor(self.device.board, 100.0, self.buzz_time)
        sleep(self.buzz_time/1000)
        
        print ("Acquisition started")           
        self.streaming = True
        libmetawear.mbl_mw_gyro_bmi160_start(self.device.board)
        libmetawear.mbl_mw_acc_start(self.device.board)
        
    def stop(self):
        e = Event()
    
        self.device.on_disconnect = lambda s: e.set()
        libmetawear.mbl_mw_debug_reset(self.device.board)
        print("Stopping ", self.device.board)
        self.streaming = False
        


if 0:
    
    mac = "CE:F3:BD:BD:04:8F"
    mbt = Sensor(mac)
    mbt.start()
    
#        
#    for s in states:
#        print("Configuring %s" % (s.device.address))
#        s.setup()
#    
#    for s in states:
#        s.start()



# signal = libmetawear.mbl_mw_settings_get_battery_state_data_signal(board)