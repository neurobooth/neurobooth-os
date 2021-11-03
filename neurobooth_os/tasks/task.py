# -*- coding: utf-8 -*-
"""
Created on Thu Oct 14 11:03:01 2021

Author: Sheraz Khan <sheraz@khansheraz.com>

License: BSD-3-Clause
"""

from __future__ import absolute_import, division
from psychopy import logging
logging.console.setLevel(logging.CRITICAL)
import os.path as op
import datetime
import time

from psychopy import visual, monitors
from psychopy import prefs
prefs.hardware['audioLib'] = ['pyo']

import neurobooth_os
from neurobooth_os.tasks import utils
import neurobooth_os.config as cfg


class Task():
    def __init__(
            self,
            instruction_file=op.join('tasks', 'assets', 'test.mp4'),
            marker_outlet=None,
            win=None,
            full_screen=False,
            text_continue_repeat=utils.text_continue_repeat,
            text_continue=utils.text_continue,
            text_practice_screen = utils.text_practice_screen,
            text_task=utils.text_task,
            text_end=utils.text_end,
            **kwargs):

        self.path_instruction_video = op.join(cfg.paths['video_tasks'], instruction_file)
        self.full_screen = full_screen
        self.events = []
        print("path to instruction video: ", self.path_instruction_video)

        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
            self.send_marker("Task-instantiated")
        else:
            self.with_lsl = False

        if win is None:
            # Setup the Window
            self.win = utils.make_win(self.full_screen)
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False


        self.instruction_video = visual.MovieStim3(
            win=self.win, filename=self.path_instruction_video, noAudio=False)

        self.continue_repeat_screen = utils.create_text_screen(self.win, text_continue_repeat)
        self.continue_screen = utils.create_text_screen(self.win, text_continue)
        self.practice_screen = utils.create_text_screen(self.win, text_practice_screen)
        self.task_screen = utils.create_text_screen(self.win, text_task)
        self.end_screen = utils.create_text_screen(self.win, text_end)


    def send_marker(self, msg=None, add_event=False):
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])
        if add_event:
            self.add_event(msg)

    def add_event(self, event_name):
        self.events.append( f'{event_name}:{datetime.now().strftime("%H:%M:%S")}')

    def present_text(self, screen, msg, func=None, audio=None, wait_time=0, win_color=(0, 0, 0), waitKeys=True,
                     first_screen=False, video_prompt=False, video=None):
        self.send_marker(f"{msg}-start_0", True)
        utils.present(self.win, screen, audio=audio, wait_time=wait_time,
                      win_color=win_color, waitKeys=waitKeys, first_screen=first_screen)
        self.send_marker(f"{msg}-end_1", True)
        if func is not None:
            if video_prompt and video is not None:
                if utils.rewind_video(self.win, self.instruction_video):
                    func()
            else:
                if utils.repeat_advance():
                    func()

    def present_video(self, video, msg, stop=False):
        self.send_marker(f"{msg}_start", True)
        utils.play_video(self.win, video, stop=stop)
        self.send_marker(f"{msg}_end", True)

    def present_instructions(self, prompt=True):
        self.present_video(video=self.instruction_video, msg='intructions')
        if prompt:
            self.present_text(screen=self.continue_repeat_screen, msg='continue-repeat', func=self.present_instructions,
                          waitKeys=False, video_prompt=True, video=self.instruction_video)

    def present_practice(self, prompt=True):
        self.present_text(screen=self.practice_screen, msg='practice')
        if prompt:
            self.present_text(screen=self.continue_repeat_screen, msg='continue-repeat', func=self.present_practice,
                          waitKeys=False)

    def present_task(self, prompt=True):
        self.present_text(screen=self.task_screen, msg='task', audio=None, wait_time=5)
        if prompt:
            self.present_text(screen=self.continue_repeat_screen, msg='continue-repeat', func=self.present_task,
                          waitKeys=False)

    def present_complete(self):
        self.present_text(screen=self.end_screen, msg='complete', audio=None, wait_time=2, waitKeys=False)

    # Close win if just created for the task
    def close(self):
        if self.win_temp:
            self.win.close()

    def run(self, prompt=True, **kwargs):
        self.present_instructions(prompt)
        self.present_practice(prompt)
        self.present_task(prompt)
        self.present_complete()
        self.close()
        return self.events



class Task_Eyetracker(Task):
    def __init__(self, eye_tracker=None, monitor_width=55, subj_screendist_cm=75,  **kwargs):
        super().__init__(**kwargs)

        self.eye_tracker = eye_tracker

        mon = monitors.getAllMonitors()[0]
        mon_size = monitors.Monitor(mon).getSizePix()
        self.SCN_W, self.SCN_H = mon_size
        self.monitor_width = monitor_width
        self.pixpercm = mon_size[0] / self.monitor_width
        self.subj_screendist_cm = subj_screendist_cm

        # prepare the pursuit target, the clock and the movement parameters
        self.win.color = [0, 0, 0]
        self.win.flip()
        self.target = visual.GratingStim(self.win, tex=None, mask='circle', size=25)

    def sendMessage(self, msg):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.sendMessage(msg)
        
    def setOfflineMode(self):
        if self.eye_tracker is not None:
            self.eye_tracker.paused = True
            self.eye_tracker.tk.setOfflineMode() 

    def startRecording(self):
        if self.eye_tracker is not None:            
            self.eye_tracker.tk.startRecording(1,1,1,1) 
            self.eye_tracker.paused = False
    
    def sendCommand(self ,msg):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.sendCommand(msg)
    
    def doDriftCorrect(self, vals):
        # vals : int, position target in screen
        if self.eye_tracker is not None:
            self.eye_tracker.tk.doDriftCorrect(vals, 0, 1)

    def gaze_contingency():
        # move task 
        pass



class Task_Dynamic_Stim(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run():
        # marker for each trial number
        pass


if __name__ == "__main__":
    task = Task()
    task.run()
