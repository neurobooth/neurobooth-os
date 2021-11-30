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

import os.path as op

import neurobooth_os
from neurobooth_os.tasks.task import Task_Eyetracker



class Fixation_Target(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def present_task(self, prompt=True, duration=3, target_pos=(0,0), **kwargs):
        self.countdown_task()
        self.target.pos = target_pos       
        self.present_text(screen=self.target, msg='task', audio=None, wait_time=duration, waitKeys=False)
        
        if prompt:
            func_kwargs = locals()
            del func_kwargs['self']
            print(func_kwargs)
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.present_task,
                          func_kwargs=func_kwargs, waitKeys=False)


if __name__ == "__main__":

    # task = Task(instruction_file=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'))
    # task.run() 

    task = Fixation_Target(instruction_file=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'))
    task.run(prompt=True, duration=3,  target_pos=(-10,-5))