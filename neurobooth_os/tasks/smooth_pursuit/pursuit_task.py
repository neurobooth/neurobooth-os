  # -*- coding: utf-8 -*-
"""
Created on Wed Nov 03 08:00:23 2021

@author: adonay
"""
import numpy as np
from math import sin, pi
import os.path as op
from psychopy import core 
import pylink
import neurobooth_os
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix, peak_vel2freq, deg2rad
from neurobooth_os.tasks.task import Task_Eyetracker


class Pursuit(Task_Eyetracker):
    def __init__(self, amplitude_deg=30, peak_velocity_deg=30, start_phase_deg=0,  ntrials=5, **kwargs):

        super().__init__(**kwargs)
        self.amplitude_deg = amplitude_deg
        self.peak_velocity_deg = peak_velocity_deg
        self.amplitude_pixel = deg2pix(self.amplitude_deg, self.subj_screendist_cm, self.pixpercm)
        self.angular_freq = peak_vel2freq(self.peak_velocity_deg, self.peak_velocity_deg)
        self.ntrials = ntrials
        # [amp_x, amp_y, phase_x, phase_y, angular_freq_x, angular_freq_y]
        self.mov_pars = [self.amplitude_pixel / 2, 0, deg2rad(start_phase_deg), 0, self.angular_freq, self.angular_freq]

    def run(self, prompt=True, **kwargs):
        self.present_instructions(prompt)        
        self.run_trial(prompt, self.mov_pars)
        self.present_complete()
        self.close()
                                              
    def run_trial(self, prompt, movement_pars):
        """ Run a smooth pursuit trial

        trial_duration: the duration of the pursuit movement
        movement_pars: [amp_x, amp_y, phase_x, phase_y, freq_x, freq_y]
        The following equation defines a sinusoidal movement pattern
        y(t) = amplitude * sin(2 * pi * frequency * t + phase)
        for circular or elliptic movements, the phase in x and y directions
        should be pi/2 (direction matters)."""

        # Parse the movement pattern parameters
        amp_x, amp_y, phase_x, phase_y, freq_x, freq_y = movement_pars

        # Take the tracker offline
        self.setOfflineMode()

        # Send the standard "TRIALID" message to mark the start of a trial
        self.sendMessage("TRIALID")

        # Record_status_message : show some info on the Host PC
        self.sendCommand("record_status_message 'Pursuit task'")

        # Drift check/correction, params, x, y, draw_target, allow_setup
        tar_x = amp_x * sin(phase_x)
        tar_y = amp_y * sin(phase_y)
        self.target.pos = (tar_x, tar_y)
        self.target.draw()
        self.win.flip()
        self.send_target_loc(self.target.pos)
        
        # self.doDriftCorrect([int(tar_x + self.mon_size[0] / 2.0),
        #                        int(self.mon_size[1] / 2.0 - tar_y), 0, 1])
 
        # Start recording
        self.startRecording()

        # Wait for 100 ms to cache some samples
        pylink.msecDelay(100)

        # Send a message to mark movement onset
        frame = 0
        time_array = []
        while True:
            # core.wait(1/480.)
            self.target.pos = (tar_x, tar_y)
            self.target.draw()
            self.win.flip()
            self.send_target_loc(self.target.pos)
            
            flip_time = core.getTime()
            frame += 1
            if frame == 1:
                self.sendMessage('Movement onset') 
                move_start = core.getTime()

            time_elapsed = flip_time - move_start
            time_array.append(flip_time)


            # update the target position
            tar_x = amp_x * sin(2 * pi * freq_x * time_elapsed + phase_x)
            tar_y = amp_y * sin(2 * pi * freq_y * time_elapsed + phase_y)

            # break if the time elapsed exceeds the trial duration
            if time_elapsed > self.ntrials * (1/freq_x):
                print(frame)  
                time_array = np.array(time_array)
                time_array = np.diff(time_array)
                print("mean time:",np.mean(time_array)*1000)
                print("med time:",np.median(time_array)*1000)
                print("std time:",np.std(time_array)*1000)
                print("max time:",np.max(time_array)*1000)
                print("min time:", np.min(time_array)*1000)
                break
        
        self.time_array = time_array   
        # clear the window
        self.win.color = (0, 0, 0)
        self.win.flip()

        # Stop recording
        self.setOfflineMode()
        # self.et.paused = True

        # Send trial variables to record in the EDF data file
        self.sendMessage(f"!V TRIAL_VAR amp_x {amp_x:.2f}")
        self.sendMessage(f"!V TRIAL_VAR amp_y {amp_y:.2f}")
        self.sendMessage(f"!V TRIAL_VAR phase_x {phase_x:.2f}")
        pylink.pumpDelay(2)  # give the tracker a break
        self.sendMessage(f"!V TRIAL_VAR phase_y {phase_y:.2f}")
        self.sendMessage(f"!V TRIAL_VAR freq_x {freq_x:.2f}")
        self.sendMessage(f"!V TRIAL_VAR freq_y {freq_y:.2f}")
        self.sendMessage(f"!V TRIAL_VAR ntrials {self.ntrials:.2f}")

        # Send a 'TRIAL_RESULT' message to mark the end of the trial
        self.sendMessage('TRIAL_RESULT')
        
        if prompt:
            func_kwargs_func = {'prompt': prompt,
                                'movement_pars': movement_pars}
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.run_trial,
                          func_kwargs=func_kwargs_func, waitKeys=False)

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    task = Pursuit(full_screen=True)
    task.run(prompt=True)

    tstmp = task.time_array
    plt.figure()
    plt.hist(tstmp, 30)
    plt.figure()
    plt.plot(tstmp )
