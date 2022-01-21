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
from neurobooth_os.tasks import utils


class Fixation_Target(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def present_task(self, prompt=True, duration=3, target_pos=(-10,5), target_size=.7, **kwargs):
        self.countdown_task()
        self.target.pos = [self.deg_2_pix(target_pos[0])/2, self.deg_2_pix(target_pos[1])/2] 
        self.target.size = self.deg_2_pix(target_size)  # target_size from deg to cms
        self.present_text(screen=self.target, msg='task', audio=None, wait_time=duration, waitKeys=False)
        
        if prompt:
            func_kwargs = locals()
            del func_kwargs['self']
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.present_task,
                          func_kwargs=func_kwargs, waitKeys=False)


class Fixation_Target_Multiple(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def present_task(self, prompt=True, duration=3, trial_pos=[(0,0), (0,15)], target_size=.7, **kwargs):
        self.countdown_task()
        for pos in trial_pos:
            self.target.pos = [self.deg_2_pix(pos[0])/2, self.deg_2_pix(pos[1])/2] 
            self.target.size = self.deg_2_pix(target_size)  # target_size from deg to cms
            self.present_text(screen=self.target, msg='trial', audio=None, wait_time=duration, waitKeys=False)
        
        if prompt:
            func_kwargs = locals()
            del func_kwargs['self']
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.present_task,
                          func_kwargs=func_kwargs, waitKeys=False)


class Fixation_Target_sidetrials(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def present_task(self, prompt=True, duration=3, target_pos=(-10,10), target_size=.7, trial_intruct=['trial 1', 'trial 2'], **kwargs):
        
        for nth, trl in enumerate(trial_intruct):            
            msg = utils.create_text_screen(self.win, trl  + "\n\n\nPress CONTINUE")
            self.send_marker(f"trial_{nth}-start", True)
            utils.present(self.win, msg)
        
            self.countdown_task()
            self.target.pos = [self.deg_2_pix(target_pos[0])/2, self.deg_2_pix(target_pos[1])/2]  
            self.target.size = self.deg_2_pix(target_size)  # target_size from deg to cms
            self.present_text(screen=self.target, msg='task', audio=None, wait_time=duration, waitKeys=False)
            
            msg = utils.create_text_screen(self.win, "Task on one side ended")
            utils.present(self.win, msg, wait_time=2, waitKeys=False)
            self.send_marker(f"trial_{nth}-end", True)
            
        if prompt:
            func_kwargs = locals()
            del func_kwargs['self']
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.present_task,
                          func_kwargs=func_kwargs, waitKeys=False)
            

if __name__ == "__main__":

    # task = Task(instruction_file=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'))
    # task.run() 

    task = Fixation_Target(instruction_file=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'))
    task.run(prompt=True, duration=3,  target_pos=(-10,-5))
    
    t = Fixation_Target_Multiple()
    t.run(duration=3, trial_pos=[(0,15), (30,15), (-30, 15)], target_size=25)
    
    t= Fixation_Target_sidetrials()
    t.run(duration=3, target_pos=(0,15), target_size=80, trial_intruct=["Do the task with your DOMINANT arm", "Do the task with your NON-DOMINANT arm"])         

