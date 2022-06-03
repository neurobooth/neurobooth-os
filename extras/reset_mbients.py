# -*- coding: utf-8 -*-
"""
Created on Fri May 27 14:49:22 2022

@author: ACQ
"""

from mbientlab.metawear import MetaWear, libmetawear
from time import sleep, time


def connect(device):
    
    try:
        device.connect()
    except:
        sleep(3)
        try:
            print('trying again...')
            device.connect()
        except:
            return False
    return True
    
    
def reset_dev(MAC):
    device = MetaWear(MAC)
    success = connect(device)
    if not success:        
        return False

    libmetawear.mbl_mw_logging_stop(device.board)
    sleep(1.0)

    libmetawear.mbl_mw_logging_flush_page(device.board)
    sleep(1.0)

    libmetawear.mbl_mw_logging_clear_entries(device.board)
    sleep(1.0)

    libmetawear.mbl_mw_event_remove_all(device.board)
    sleep(1.0)

    libmetawear.mbl_mw_macro_erase_all(device.board)
    sleep(1.0)

    libmetawear.mbl_mw_debug_reset_after_gc(device.board)
    sleep(1.0)

    libmetawear.mbl_mw_debug_disconnect(device.board)
    sleep(1.0)

    device.disconnect()
    sleep(1.0)
    return True


if __name__ == '__main__':
    macs = {
        'Mbient_LH_2': 'E8:95:D6:F7:39:D2',
        'Mbient_RH_2': 'FE:07:3E:37:F5:9C',
        'Mbient_RF_2': 'E5:F6:FB:6D:11:8A',
        'Mbient_LF_2': 'DA:B0:96:E4:7F:A3',
        'Mbient_BK_1': 'D7:B0:7E:C2:A1:23'
        }
    
    print('resetting mbients (will take ~ 1 min)...')

    for k, v in macs.items():
        success = reset_dev(v)
        if not success:
            print(f"Failed to connect {k} {v}")
        else:
            print(f"Success in resetting {k} {v}")
