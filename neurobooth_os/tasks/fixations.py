# -*- coding: utf-8 -*-
"""
Created on Mon Nov 22 11:24:12 2021

@author: STM
"""

# -*- coding: utf-8 -*-
"""
Created on Mon Nov 22 11:22:32 2021

@author: STM
"""

from neurobooth_os.tasks.task import Task_Eyetracker



class Fixation_Target(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def present_task(self, prompt=True, duration=3, target_pos=(0,0), **kwargs):
        self.countdown_task()
        self.target.pos = target_pos       
        self.present_text(screen=self.target, msg='task', audio=None, wait_time=duration, waitKeys=False)
        
        if prompt:
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.present_task,
                          func_kwargs=locals(), waitKeys=False)
  