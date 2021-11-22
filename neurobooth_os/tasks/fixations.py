# -*- coding: utf-8 -*-
"""
Created on Mon Nov 22 10:19:48 2021

@author: Adonay nunes
"""

import os.path as op
import random
import time
from datetime import datetime
import numpy as np
import pandas as pd

from psychopy import core, visual, event

import neurobooth_os
from neurobooth_os.tasks import utils
from neurobooth_os.tasks.task import Task_Eyetracker



class Fixation_Target(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def present_task(self, duration, prompt=True, target_pos=(0,0)):
        self.countdown_task()
        self.target.pos = target_pos       
        self.present_text(screen=self.target, msg='task', audio=None, wait_time=duration, waitKeys=False)
        
        if prompt:
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.present_task,
                          waitKeys=False)
  
    
            