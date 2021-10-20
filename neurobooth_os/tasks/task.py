# -*- coding: utf-8 -*-
"""
Created on Thu Oct 14 11:03:01 2021

Author: Sheraz Khan <sheraz@khansheraz.com>

License: BSD-3-Clause
"""

import os.path as op

from __future__ import absolute_import, division
from psychopy import logging
logging.console.setLevel(logging.CRITICAL)

from psychopy import visual
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


    def send_marker(self, msg=None):
        if self.with_lsl:
            utils.send_marker(self.marker, msg)

    def present_text(self, screen, msg, func=None, audio=None, wait_time=0, win_color=(0, 0, 0), waitKeys=True,
                     first_screen=False, video_prompt=False, video=None):
        self.send_marker(f"{msg}-start_0")
        utils.present(self.win, screen, audio=audio, wait_time=wait_time,
                      win_color=win_color, waitKeys=waitKeys, first_screen=first_screen)
        self.send_marker(f"{msg}-end_1")
        if func is not None:
            if video_prompt and video is not None:
                if utils.rewind_video(self.win, self.instruction_video):
                    func()
            else:
                if utils.repeat_advance():
                    func()

    def present_video(self, video, msg, stop=False):
        self.send_marker(f"{msg}_start")
        utils.play_video(self.win, video, stop=stop)
        self.send_marker(f"{msg}_end")

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
        print('starting task')
        self.present_instructions(prompt)
        print('starting instructions')
        self.present_practice(prompt)
        print('starting task')
        self.present_task(prompt)
        print('end screen')
        self.present_complete()
        print('close window')
        self.close()
        print('task done')


if __name__ == "__main__":
    task = Task()
    utils.run_task(task, prompt=True)