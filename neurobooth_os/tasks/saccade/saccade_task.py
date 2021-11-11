# -*- coding: utf-8 -*-
"""
Created on Wed Nov 03 08:00:23 2021

@author: Sheraz Khan: sheraz@khansheraz.com
"""
from math import sin, pi
import os.path as op
from psychopy import core 
import pylink
import neurobooth_os
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix, peak_vel2freq, deg2rad
from neurobooth_os.tasks.task import Task_Eyetracker
import numpy as np


class Saccade(Task_Eyetracker):
    def __init__(self, amplitude_deg=30, direction='horizontal',  wait_center =1, Wait_offset=1,
                jitter_percent=0.5, pointer_size_deg=0.7 , trial_sign=[-1, -1, 1, -1, 1, -1, 1, 1, -1, -1, 1, 1], **kwargs):    
    # amplitude_deg=30, peak_velocity_deg=33.3, **kwargs):

        super().__init__(**kwargs)
        self.amplitude_deg = amplitude_deg
        self.direction = direction
        self.amplitude_pixel = deg2pix(self.amplitude_deg, self.subj_screendist_cm, self.pixpercm)
        self.trial_sign = trial_sign
        self.ntrials = len(trial_sign)
        self.wait_center = wait_center
        self.wait_offset = Wait_offset
        self.jitter_percent = jitter_percent
        self.pointer_size_deg = pointer_size_deg
        self.pointer_size_pixel = deg2pix(self.pointer_size_deg, self.subj_screendist_cm, self.pixpercm)
        # [-amp_x, amp_y]
        if direction == 'horizontal':
            self.movement_pars = [self.amplitude_pixel / 2, 0]
        elif direction == 'vertical':
            self.movement_pars = [0, self.amplitude_pixel / 2]
        else:
            raise ValueError("Only horizontal and vertical saccade is supported")

    def run(self, **kwargs):
        self.present_instructions(True)        
        self.run_trials()
        self.present_complete()
        self.close()

                                              
    def run_trials(self):
        """ Run a smooth pursuit trial"""

        # Parse the movement pattern parameters
        amp_x, amp_y = self.movement_pars
        tar_x = amp_x
        tar_y = amp_y

        # Take the tracker offline
        self.setOfflineMode()

        # Send the standard "TRIALID" message to mark the start of a trial
        self.sendMessage("TRIALID")

        # Record_status_message : show some info on the Host PC
        self.sendCommand("record_status_message 'Pursuit task'")

        # Drift check/correction, params, x, y, draw_target, allow_setup

        self.target.pos = (0, 0)
        self.target.size = self.pointer_size_pixel
        self.target.draw()
        self.win.flip()
        self.doDriftCorrect([int(0 + self.mon_size[0] / 2.0),
                               int(self.mon_size[1] / 2.0 - 0), 0, 1])
        self.win.color = (0, 0, 0)
        self.win.flip()
 
        # Start recording
        self.startRecording()

        # Wait for 100 ms to cache some samples
        pylink.msecDelay(100)

        # Send a message to mark movement onset
        frame = 0
        for index in range(self.ntrials):

            self.target.pos = (0, 0)
            self.target.size = self.pointer_size_pixel
            self.target.draw()
            self.win.flip()
            tar_msg = f'!V TARGET_POS Center {0}, {0} 1 0'
            self.sendMessage(tar_msg)
            core.wait(self.wait_center + self.jitter_percent*self.wait_center*np.random.random(1)[0])

            self.target.pos = (tar_x, tar_y)
            self.target.size = self.pointer_size_pixel
            self.target.draw()
            self.win.flip()
            flip_time = core.getTime()
            frame += 1
            if frame == 1:
                self.sendMessage('Movement_onset')
                move_start = core.getTime()
            else:
                _x = int(tar_x + self.SCN_W / 2.0)
                _y = int(self.SCN_H / 2.0 - tar_y)
                tar_msg = f'!V TARGET_POS target {_x}, {_y} 1 0'
                self.sendMessage(tar_msg)

            time_elapsed = flip_time - move_start

            # update the target position
            

            tar_x = self.trial_sign[index] * amp_x 
            tar_y = self.trial_sign[index] * amp_y 

            core.wait(self.wait_offset + self.jitter_percent*self.wait_offset*np.random.random(1)[0])
        # clear the window

        self.win.color = (0, 0, 0)
        self.win.flip()

        # Stop recording
        self.setOfflineMode()
        # self.et.paused = True

        # Send trial variables to record in the EDF data file
        self.sendMessage(f"!V TRIAL_VAR amp_x {amp_x:.2f}")
        self.sendMessage(f"!V TRIAL_VAR amp_y {amp_y:.2f}")
        pylink.pumpDelay(2)  # give the tracker a break
        self.sendMessage(f"!V TRIAL_VAR ntrials {self.ntrials:.2f}")

        # Send a 'TRIAL_RESULT' message to mark the end of the trial
        self.sendMessage('TRIAL_RESULT')

if __name__ == "__main__":
    
    task = Saccade(instruction_file=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'))
    task.run()
    task = Saccade(direction='vertical', amplitude_deg=15, instruction_file=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'))
    task.run()
