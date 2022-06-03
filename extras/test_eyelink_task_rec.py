# -*- coding: utf-8 -*-
"""
Created on Thu Aug 12 14:08:29 2021

@author: STM
"""

import socket 
import io
import pandas as pd
import sys
import os
from time import time, sleep  
from neurobooth_os import config

from neurobooth_os.iout.screen_capture import ScreenMirror
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient
from neurobooth_os.netcomm.client import socket_message, node_info
from neurobooth_os.tasks.test_timing.audio_video_test import Timing_Test
from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_funcs

os.chdir(r'C:\neurobooth-eel\neurobooth_os\\')
print(os.getcwd())

def fake_task(**kwarg):
    sleep(10)
    


def run_task(task_funct, s2, cmd, subj_id, task, send_stdout, task_karg={}):    
    resp = socket_message(f"record_start:{subj_id}_{task}", "acquisition", wait_data=2)
    print(resp)
    s2.sendall(cmd.encode('utf-8') )
    sleep(.5)
    s2.sendall(b"select all\n")
    sleep(.5)
    s2.sendall(b"start\n")
    sleep(.5)
    res = task_funct(**task_karg)
    s2.sendall(b"stop\n")
    socket_message("record_stop", "acquisition")
    sleep(2)
    return res
                
   

win = utl.make_win(full_screen=False)
streams, screen_running = {}, False            
collection_id = "mvp_025"
streams = start_lsl_threads("presentation", collection_id, win=win)
task_func_dict = get_task_funcs(collection_id) 

task = 'pursuit_task_1'              
subj_id = "me"    

win.color = [0,0,0]
win.flip()     
task_karg ={"win": win,
            "path": config.paths['data_out'],
            "subj_id": subj_id,
            "eye_tracker": streams['eye_tracker'],
            "marker_outlet": streams['marker'],
            "event_marker": streams['marker']}


tsk_fun = task_func_dict[task] 


# res = run_task(tsk_fun, s2, cmd, subj_id, task, send_stdout, task_karg)

tsk_fun(**task_karg)
streams['eye_tracker'].stop()


# fname =  f"{config.paths['data_out']}{subj_id}{task}2.edf"
# streams['eye_tracker'].start(fname)

# # res = run_task(tsk_fun, s2, cmd, subj_id, task, send_stdout, task_karg)

# tsk_fun(**task_karg)
# streams['eye_tracker'].stop()                    

                    
win.close()
