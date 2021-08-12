# -*- coding: utf-8 -*-
"""
Created on Mon Jul 19 11:20:57 2021

@author: STM
"""
import os
from time import time, sleep  
import config
from neurobooth_os.tasks.DSC import DSC
from neurobooth_os.tasks.mouse import mouse_task
from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
from neurobooth_os.tasks.test_timing.audio_video_test import Timing_Test
from neurobooth_os.tasks.sit_to_stand.experiment import Sit_to_Stand
from neurobooth_os.iout.eyelink_tracker import EyeTracker
from neurobooth_os.tasks.smooth_pursuit.pursuit_task import pursuit
from neurobooth_os.tasks.utils import make_win

os.chdir(r'C:\neurobooth-eel\\')

def run_task(task_funct, task_karg={}):    
    res = task_funct(**task_karg)
    return res

streams = {}
streams['marker'] = None


win = welcome_screen(False)

et = EyeTracker(win=win)
et.calibrate()
subj_id = "test"



et.filename = 'pursuit.edf'
et.start(filename=et.filename)


task_karg ={"win": win,            
            "subj_id": subj_id,
            "marker_outlet": streams['marker'],
            "eye_tracker": et}

res = run_task(pursuit, task_karg)



# task_karg ={"win": win,
#             "path": config.paths['data_out'],
#             "subj_id": subj_id,
#             "marker_outlet": streams['marker']}

# res = run_task(mouse_task, task_karg)  
  
# task_karg ={"win": win,
#             "marker_outlet": streams['marker']}
# res = run_task(DSC, task_karg)


# task_karg ={"win": win,
#              "marker_outlet": streams['marker']}             
# run_task(Sit_to_Stand, task_karg)

# finish_screen(win)
