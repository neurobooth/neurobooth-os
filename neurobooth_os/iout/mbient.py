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
    def __init__(self, mac, dev_name="mbient", acc_hz =100, gyro_hz=200, buzz_time_sec=2):
        
        self.mac = mac
        self.dev_name = dev_name
        self.connector = MetaWear
        self.connect()
        
        self.processor = None
        self.buzz_time = buzz_time_sec *1000
        self.acc_hz = acc_hz
        self.gyro_hz = gyro_hz
        
        # Setup outlet stream infos
        self.oulet_id =  str(uuid.uuid4())
        self.stream_mbient = StreamInfo(name=f'mbient_{self.dev_name}', type='acc',
                                        channel_count=6, channel_format='float32',
                                        source_id=self.oulet_id)    
        
        
        self.streaming = False        
        self.setup()
        print(f"-OUTLETID-:mbient_{self.dev_name}:{self.oulet_id}")
       
    def connect(self):        
        self.device = self.connector(self.mac)
        self.device.connect()       
        print(f"Mbient {self.dev_name} connected")
        
        
    def data_handler(self, ctx, data):
        values = parse_value(data, n_elem = 2)
        vals = [values[0].x, values[0].y, values[0].z, values[1].x, values[1].y, values[1].z]
        
        self.outlet.push_sample(vals)
        # print("acc: (%.4f,%.4f,%.4f), gyro; (%.4f,%.4f,%.4f)" % (values[0].x, values[0].y, values[0].z, values[1].x, values[1].y, values[1].z))


    def setup(self):
        libmetawear.mbl_mw_settings_set_connection_parameters(self.device.board, 7.5, 7.5, 0, 6000)
        sleep(1.5)
        
        libmetawear.mbl_mw_acc_set_odr(self.device.board, self.acc_hz)
        libmetawear.mbl_mw_acc_set_range(self.device.board, 16.0)
        libmetawear.mbl_mw_gyro_bmi160_set_odr(self.device.board, self.gyro_hz)
        libmetawear.mbl_mw_gyro_bmi160_set_range(self.device.board, 2000)
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
        
        print(f"Mbient {self.dev_name} setup")
        
    def info(self):
        
        dev_info = self.device.info
        
        def battery_handler(self, ctx, data):
            value = parse_value(data, n_elem=1)
            print("Voltage: {0}, Charge: {1}".format(
                value.voltage, value.charge))
    
        signal = libmetawear.mbl_mw_settings_get_battery_state_data_signal(self.device.board)
         
        
        voltage = libmetawear.mbl_mw_datasignal_get_component(signal, cbindings.Const.SETTINGS_BATTERY_VOLTAGE_INDEX)
        charge = libmetawear.mbl_mw_datasignal_get_component(signal, cbindings.Const.SETTINGS_BATTERY_CHARGE_INDEX)
        
        libmetawear.mbl_mw_datasignal_subscribe(charge, None, battery_handler)
    
    def start(self):
        print(f"Started mbient{self.dev_name}")
        libmetawear.mbl_mw_gyro_bmi160_enable_rotation_sampling(self.device.board)
        libmetawear.mbl_mw_acc_enable_acceleration_sampling(self.device.board)
        
        # Vibrate for 7 secs and then start aqc
        libmetawear.mbl_mw_haptic_start_motor(self.device.board, 100.0, self.buzz_time)
        sleep(self.buzz_time/1000)
        
        # print ("Acquisition started")           
        self.streaming = True
        libmetawear.mbl_mw_gyro_bmi160_start(self.device.board)
        libmetawear.mbl_mw_acc_start(self.device.board)
        
    def stop(self):
        e = Event()
    
        self.device.on_disconnect = lambda s: e.set()
        libmetawear.mbl_mw_debug_reset(self.device.board)
        print("Stopping ", self.dev_name)
        self.streaming = False
    
    def close(self):
       self.device.on_disconnect = lambda status: print (f"Mbient {self.dev_name} disconnected!")
       self.device.disconnect()
        


if 0:
    
    mac = "EE:99:D8:9D:69:5F"
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