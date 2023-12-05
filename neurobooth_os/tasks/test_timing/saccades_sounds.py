# -*- coding: utf-8 -*-
"""
Created on Wed Nov 03 08:00:23 2021

@author: Sheraz Khan: sheraz@khansheraz.com
"""
from psychopy import prefs

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

from math import sin, pi
import os.path as op
import numpy as np
from pylsl import local_clock
from psychopy import core, sound
import pylink

import neurobooth_os
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix, peak_vel2freq, deg2rad
from neurobooth_os.tasks.task import Task_Eyetracker


def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()


class Saccade_synch(Task_Eyetracker):
    def __init__(self, wait_center=1, target_size=0.7, num_iterations=10, monochrome=True, **kwargs):

        super().__init__(**kwargs)
        self.ntrials = int(num_iterations)
        self.wait_center = wait_center
        self.pointer_size_deg = target_size
        self.pointer_size_pixel = deg2pix(
            self.pointer_size_deg, self.subj_screendist_cm, self.pixpercm
        )

        if monochrome:
            self.color_sequence = ["black", "white", "black", "white"]
        else:
            self.color_sequence = ["green", "red", "green", "blue"]

        self.target_positions = [(0, 0), (-480, 0), (0, 0), (480, 0)]

    def run(self, prompt=True, last_task=False):
        self.present_instructions(prompt)
        self.run_trials(prompt)
        self.present_complete(last_task)
        return self.events

    def run_trials(self, prompt=True):
        """Run a smooth pursuit trial"""

        # Take the tracker offline
        # self.setOfflineMode()

        # Record_status_message : show some info on the Host PC
        # self.sendCommand("record_status_message 'Pursuit task'")

        # Drift check/correction, params, x, y, draw_target, allow_setup

        self.target.pos = self.target_positions[0]
        self.target.size = self.pointer_size_pixel
        # self.target.draw()
        # self.win.flip()
        # self.doDriftCorrect([int(0 + self.mon_size[0] / 2.0),
        #                        int(self.mon_size[1] / 2.0 - 0), 0, 1])
        self.win.color = self.color_sequence[0]
        self.win.flip()

        # self.sendMessage("TRIALID")
        # Start recording
        # self.startRecording()

        # Wait for 100 ms to cache some samples
        # pylink.msecDelay(100)
        mySound = sound.Sound(1000, 0.1, stereo=True)

        # Send a message to mark movement onset
        self.sendMessage(self.marker_task_start)
        n_nosound = 0
        for ix in range(self.ntrials):
            for tgt_pos, color in zip(self.target_positions, self.color_sequence):
                self.win.color = color
                self.win.flip()
                if ix >= n_nosound:
                    mySound.play(when=self.win.getFutureFlipTime(clock="ptb"))
                self.target.pos = tgt_pos
                self.target.draw()
                self.win.flip()
                self.sendMessage(self.marker_trial_start)
                self.send_target_loc(self.target.pos)

                countdown(self.wait_center)

        # clear the window
        self.win.color = (0, 0, 0)
        self.win.flip()

        # Stop recording
        self.setOfflineMode()

        self.sendMessage(self.marker_task_end)

        if prompt:
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.run_trials,
                waitKeys=False,
            )


if __name__ == "__main__":

    task = Saccade_synch()
    task.run(prompt=False)
