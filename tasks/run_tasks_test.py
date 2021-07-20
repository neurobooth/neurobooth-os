# -*- coding: utf-8 -*-
"""
Created on Mon Jul 19 11:20:57 2021

@author: STM
"""

from time import time, sleep  
import config
from tasks.DSC import DSC
from tasks.mouse import mouse_task
from tasks.wellcome_finish_screens import welcome_screen, finish_screen
from tasks.test_timing.audio_video_test import Timing_Test
from tasks.sit_to_stand.experiment import Sit_to_Stand
from iout.eyelink_tracker import EyeTracker
 
def run_task(task_funct, task_karg={}):    
    res = task_funct(**task_karg)
    return res

streams = {}
streams['marker'] = None

tasks = [Sit_to_Stand, DSC, mouse_task]

win = welcome_screen()

et = EyeTracker( win=win)
et.calibrate()
subj_id = "test"

task_karg ={"win": win,
            "path": config.paths['data_out'],
            "subj_id": subj_id,
            "marker_outlet": streams['marker']}

res = run_task(tasks[2], task_karg)  
  
task_karg ={"win": win,
            "marker_outlet": streams['marker']}
res = run_task(tasks[1], task_karg)


task_karg ={"win": win,
             "marker_outlet": streams['marker']}             
run_task(Sit_to_Stand, task_karg)

finish_screen(win)
