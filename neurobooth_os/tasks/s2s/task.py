from __future__ import absolute_import, division
import neurobooth_os
import os.path as op
from neurobooth_os.tasks.utils import make_win
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
            text_practice=utils.text_practice,
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
            self.win = make_win(self.full_screen)
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False


        self.instruction_video = visual.MovieStim3(
            win=self.win, filename=self.path_instruction_video, noAudio=False)


        self.practice = utils.create_text_screen(self.win, text_practice)
        self.task = utils.create_text_screen(self.win, text_task)
        self.end = utils.create_text_screen(self.win, text_end)


    def send_marker(self, msg=None):
        if self.with_lsl:
            utils.send_marker(self.marker, msg)


    def instructions(self):
        while True:
            self.send_marker("Intructions-start_0")
            utils.play_video(self.win, self.instruction_video, stop=False)
            self.send_marker("Intructions-end_1")

            self.send_marker("Practice-Intructions-start_0")
            utils.present(self.win, self.practice, waitKeys=False)
            self.send_marker("Practice-Intructions-end_1")

            if not utils.rewind_video(self.win, self.instruction_video):
                break


    def run(self):
        self.send_marker("Task-start_0")
        utils.present(self.win, self.task, audio=None, wait_time=5)
        self.send_marker("Task-end_0")

        self.send_marker("Task-complete_0")
        utils.present(self.win, self.end, audio=None, wait_time=2, waitKeys=False)
        self.send_marker("Task-complete_0")

        # Close win if just created for the task
        if self.win_temp:
            self.win.close()


if __name__ == "__main__":

    sts = Sit_to_Stand()
    sts.instructions()
    sts.run()