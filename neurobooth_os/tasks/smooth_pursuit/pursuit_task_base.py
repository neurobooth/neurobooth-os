# -*- coding: utf-8 -*-
"""
Created on Wed Nov 03 08:00:23 2021

@author: adonay
"""
import random
from math import sin, pi

from psychopy import core 
import pylink

from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix, peak_vel2freq
from neurobooth_os.tasks.task import Task_Eyetracker


class pursuit(Task_Eyetracker):
    def __init__(self, amplitude_deg, peak_velocity_deg,  **kwargs):    
    # amplitude_deg=30, peak_velocity_deg=33.3, **kwargs):

        super().__init__(**kwargs)
        self.amplitude_deg = amplitude_deg
        self.peak_velocity_deg = peak_velocity_deg
        self.amplitude_pixel = deg2pix(self.amplitude_deg, self.subj_screendist_cm, self.pixpercm)
        self.angular_freq = peak_vel2freq(self.peak_velocity_deg, self.peak_velocity_deg)

        self._task_setup()

    def _task_setup(self):
        # Parameters for the Sinusoidal movement pattern
        # [amp_x, amp_y, phase_x, phase_y, angular_freq_x, angular_freq_y]
        self.mov_pars = [
            [self.amplitude_pixel / 2, 0, 0, 0, self.angular_freq, self.angular_freq],
            [self.amplitude_pixel / 2, 0, 0, 0, self.angular_freq, self.angular_freq],
            [self.amplitude_pixel / 2, 0, 0, 0, self.angular_freq, self.angular_freq],
            [self.amplitude_pixel / 2, 0, 0, 0, self.angular_freq, self.angular_freq]
        ]

    def run(self, **kwargs):
        # Run a block of 2 trials, in random order
        test_list = self.mov_pars
        random.shuffle(test_list)
        for trial in test_list:
            self.run_trial(8.0, trial)


    def run_trial(self, trial_duration, movement_pars):
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
        self.doDriftCorrect(int(tar_x + self.mon_size[0] / 2.0),
                               int(self.mon_size[1] / 2.0 - tar_y), 0, 1)
 
        # Start recording
        # params: file_sample, file_event, link_sampe, link_event (1-yes, 0-no)
        self.startRecording(1, 1, 1, 1)

        # Wait for 100 ms to cache some samples
        pylink.msecDelay(100)

        # Send a message to mark movement onset
        frame = 0
        while True:
            self.target.pos = (tar_x, tar_y)
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
            tar_x = amp_x * sin(2 * pi * freq_x * time_elapsed + phase_x)
            tar_y = amp_y * sin(2 * pi * freq_y * time_elapsed + phase_y)

            # break if the time elapsed exceeds the trial duration
            if time_elapsed > trial_duration:
                break

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
        self.sendMessage(f"!V TRIAL_VAR duration {trial_duration:.2f}")

        # Send a 'TRIAL_RESULT' message to mark the end of the trial
        self.sendMessage('TRIAL_RESULT')
