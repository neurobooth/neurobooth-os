from __future__ import absolute_import, division
from psychopy import logging
logging.console.setLevel(logging.CRITICAL)

import neurobooth_os
import os.path as op
from neurobooth_os.tasks import utils
from psychopy import visual
from psychopy import prefs
prefs.hardware['audioLib'] = ['pyo']


class Sit_to_Stand():
    def __init__(
            self,
            path_instruction_video=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'),
            marker_outlet=None,
            win=None,
            full_screen=False,
            text_continue_repeat=utils.text_continue_repeat,
            text_continue=utils.text_continue,
            text_practice_screen = utils.text_practice_screen,
            text_task=utils.text_task,
            text_end=utils.text_end):

        self.path_instruction_video = path_instruction_video
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

    def present_text(self, screen, msg, audio=None, wait_time=0, win_color=(0, 0, 0), waitKeys=True, first_screen=False):
        self.send_marker(f"{msg}-start_0")
        utils.present(self.win, screen, audio=audio, wait_time=wait_time,
                      win_color=win_color, waitKeys=waitKeys, first_screen=first_screen)
        self.send_marker(f"{msg}-end_1")

    def present_video(self, video, msg, stop=False):
        self.send_marker(f"{msg}-start_0")
        utils.play_video(self.win, video, stop=stop)
        self.send_marker(f"{msg}-end_1")

    def instructions(self, prompt=True):
        self.present_video(video=self.instruction_video, msg='intructions')
        self.present_text(screen=self.continue_repeat_screen, msg='continue-repeat', waitKeys=False)
        # Requires user or coordinator input to terminate
        if prompt:
            if utils.rewind_video(self.win, self.instruction_video):
                self.instructions()

    def practice(self, prompt=True):
        self.present_text(screen=self.practice_screen, msg='practice')
        self.present_text(screen=self.continue_repeat_screen, msg='continue-repeat', waitKeys=False)
        # Requires user or coordinator input to terminate
        if prompt:
            if utils.repeat_advance():
                self.practice()

    def run(self, prompt=True):
        self.present_text(screen=self.task_screen, msg='task', audio=None, wait_time=5)
        self.present_text(screen=self.continue_repeat_screen, msg='continue-repeat', waitKeys=False)
        # Requires user or coordinator input to terminate
        if prompt:
            if utils.repeat_advance():
                self.run()

    def complete(self):
        self.present_text(screen=self.end_screen, msg='complete', audio=None, wait_time=2, waitKeys=False)

    # Close win if just created for the task
    def close(self):
        if self.win_temp:
            self.win.close()


if __name__ == "__main__":
    sts = Sit_to_Stand()
    utils.run_task(sts)