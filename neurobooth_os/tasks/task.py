# -*- coding: utf-8 -*-
"""
 A task is an operation or sequence of steps performed presented to a subject via Psychopy.
"""

from __future__ import absolute_import, division

from typing import List

from psychopy import logging as psychopy_logging

psychopy_logging.console.setLevel(psychopy_logging.CRITICAL)
import logging
import os.path as op
from datetime import datetime
import time

from psychopy import visual, monitors, sound, event

import neurobooth_os
from neurobooth_os.tasks import utils
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix
from neurobooth_os.log_manager import APP_LOG_NAME


class Task:
    # Note: incorrect file paths passed to Psychopy may cause the python interpreter to crash without raising an error.
    # These file paths must be checked before passing and an appropriate error raised, and so they
    # are checked inline below.
    # We cannot check paths with pydantic when loading the params because the path strings there are partial.
    def __init__(
            self,
            instruction_file=None,
            marker_outlet=None,
            win=None,
            full_screen: bool = False,
            text_continue_repeat=utils.text_continue_repeat,
            text_continue=utils.text_continue,
            text_practice_screen=utils.text_practice_screen,
            text_task=utils.text_task,
            text_end=utils.text_end,
            countdown=None,
            task_repeatable_by_subject: bool = True,
            **kwargs,
    ):
        super().__init__()
        self.logger = logging.getLogger(APP_LOG_NAME)

        # Common markers
        self.marker_task_start = "Task_start"
        self.marker_task_end = "Task_end"
        self.marker_trial_start = "Trial_start"
        self.marker_trial_end = "Trial_end"
        self.marker_practice_trial_start = "PracticeTrial_start"
        self.marker_practice_trial_end = "PracticeTrial_end"
        self.marker_response_start = "Response_start"
        self.marker_response_end = "Response_end"

        self.task_files: List[str] = []
        self.path_instruction_video = instruction_file
        self.full_screen = full_screen
        self.events = []
        self.advance_keys = ['space']
        if task_repeatable_by_subject:
            task_end_image = "tasks/assets/task_end.png"
            self.repeat_keys = ['r', 'comma']
        else:
            task_end_image = "tasks/assets/task_end_disabled.png"
            self.repeat_keys = ['r']

        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet

        else:
            self.with_lsl = False

        if win is None:
            # Set up the Window
            self.win = utils.make_win(self.full_screen)
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False

        if self.path_instruction_video is not None:
            self.instruction_video = visual.MovieStim3(
                win=self.win, filename=self.path_instruction_video, noAudio=False
            )
        else:
            self.instruction_video = None

        # Create mouse and set not visible
        self.Mouse = event.Mouse(visible=False, win=self.win)
        self.Mouse.setVisible(0)

        self.root_pckg = neurobooth_os.__path__[0]

        inst_end_task_img = op.join(self.root_pckg, "tasks", "assets", "inst_end_task.png")
        if not op.isfile(inst_end_task_img):
            raise IOError(f'Required image file {inst_end_task_img} does not exist')
        self.press_inst_screen = visual.ImageStim(
            self.win,
            image=inst_end_task_img,
            pos=(0, 0),
            units="deg",
        )

        task_end_img = op.join(self.root_pckg, task_end_image)
        if not op.isfile(task_end_img):
            raise IOError(f'Required image file {task_end_image} does not exist')

        self.press_task_screen = visual.ImageStim(
            self.win,
            image=task_end_image,
            pos=(0, 0),
            units="deg",
        )
        if countdown is None:
            countdown = "countdown_2021_11_22.mp4"
        countdown_path = op.join(neurobooth_os.__path__[0], "tasks", "assets", countdown)
        if not op.isfile(countdown_path):
            raise IOError(f'Required image file {countdown_path} does not exist')
        self.countdown_video = visual.MovieStim3(
            win=self.win,
            filename=countdown_path,
            noAudio=False,
        )

        self.continue_screen = utils.create_text_screen(self.win, text_continue)
        self.practice_screen = utils.create_text_screen(self.win, text_practice_screen)
        self.task_screen = utils.create_text_screen(self.win, text_task)
        task_complete_img = op.join(self.root_pckg, "tasks", "assets", "task_complete.png")
        if not op.isfile(task_complete_img):
            raise IOError(f'Required image file {task_complete_img} does not exist')

        self.end_screen = visual.ImageStim(
            self.win,
            image=task_complete_img,
            pos=(0, 0),
            units="deg",
        )
        end_slide = op.join(self.root_pckg, "tasks", "assets", "end_slide_3_7_22.jpg")
        if not op.isfile(end_slide):
            raise IOError(f'Required image file {end_slide} does not exist')

        self.end_tasks = visual.ImageStim(
            self.win,
            image=end_slide,
            pos=(0, 0),
            units="deg",
        )

    def repeat_advance(self):
        """
         Repeat the current task or continue to next, based on the key pressed.
         :returns: False to continue; True to repeat
         """
        keys = utils.get_keys(keyList=[*self.advance_keys, *self.repeat_keys])
        for key in keys:
            if key in self.advance_keys:
                return False
            elif key in self.repeat_keys:
                return True
        self.logger.warning(f'Unreachable case during task repeat_advance: keys={keys}')

    def send_marker(self, msg=None, add_event=False):
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])
        if add_event:
            self.add_event(msg)

    def add_event(self, event_name):
        self.events.append(f"{event_name}:{datetime.now().strftime('%H:%M:%S')}")

    def show_text(
            self,
            screen,
            msg,
            func=None,
            func_kwargs=None,
            audio=None,
            wait_time=0,
            win_color=(0, 0, 0),
            waitKeys=True,
            first_screen=False,
    ):

        if func_kwargs is None:
            func_kwargs = {}
        self.send_marker(f"{msg}_start", True)
        utils.present(
            self.win,
            screen,
            audio=audio,
            wait_time=wait_time,
            win_color=win_color,
            waitKeys=waitKeys,
            first_screen=first_screen,
        )
        self.send_marker(f"{msg}_end", True)

        if func is not None:
            if self.repeat_advance():
                func(**func_kwargs)

    def show_video(self, video, msg, stop=False):
        self.send_marker(f"{msg}_start", True)
        if video is not None:
            utils.play_video(self.win, video, stop=stop)
        self.send_marker(f"{msg}_end", True)

    def countdown_task(self):
        mySound = sound.Sound(1000, 0.2, stereo=True)
        utils.play_video(self.win, self.countdown_video, wait_time=4, stop=False)
        mySound.play()
        utils.countdown(0.22)

    def present_instructions(self, prompt=True):
        self.show_video(video=self.instruction_video, msg="Intructions")
        if prompt:
            self.show_text(
                screen=self.press_inst_screen,
                msg="Intructions-continue-repeat",
                func=self.present_instructions,
                waitKeys=False,
            )

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.countdown_task()
        self.show_text(screen=self.task_screen, msg="Task", audio=None, wait_time=3)
        if prompt:
            print(locals())
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                waitKeys=False,
            )

    def present_complete(self, last_task=False):
        if last_task:
            screen = self.end_tasks
        else:
            screen = self.end_screen
        self.show_text(
            screen=screen, msg="Completed-task", audio=None, wait_time=0, waitKeys=False
        )
        self.close()

    # Close videos and win if just created for the task
    def close(self):
        if self.instruction_video is not None:
            self.instruction_video.stop()
        self.countdown_video.stop()
        if self.win_temp:
            self.win.close()

    def run(self, prompt=True, duration=0, last_task=False, **kwargs):
        self.present_instructions(prompt)
        self.present_task(prompt, duration, **kwargs)
        self.present_complete(last_task)
        return self.events


class Task_countdown(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(self, prompt, duration, **kwargs):
        self.countdown_task()

        self.send_marker(self.marker_task_start, True)
        utils.present(self.win, self.task_screen, waitKeys=False)
        utils.countdown(duration + 2)
        self.win.flip()
        self.send_marker(self.marker_task_end, True)

        if prompt:
            func_kwargs = locals()
            del func_kwargs["self"]
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                func_kwargs=func_kwargs,
                waitKeys=False,
            )


class Task_pause(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.screen = None

    def run(self, slide_image="end_slide_3_7_22.jpg", wait_key="return", **kwarg):
        image_path = op.join(self.root_pckg, "tasks", "assets", slide_image)
        if not op.isfile(image_path):
            raise IOError(f'Required slide image file {image_path} does not exist.')

        self.screen = visual.ImageStim(
            self.win,
            image=image_path,
            pos=(0, 0),
            units="deg",
        )

        self.screen.draw()
        self.win.flip()
        utils.get_keys(keyList=[wait_key])
        self.win.flip()


class Task_Eyetracker(Task):
    def __init__(self, eye_tracker=None, target_size=7, **kwargs):
        super().__init__(**kwargs)

        self.eye_tracker = eye_tracker

        mon = monitors.getAllMonitors()[1]
        self.mon_size = monitors.Monitor(mon).getSizePix()
        self.SCN_W, self.SCN_H = self.mon_size
        self.monitor_width = self.win.monitor.getWidth()
        self.pixpercm = self.mon_size[0] / self.monitor_width
        self.subj_screendist_cm = self.win.monitor.getDistance()

        self.target_size_pix = self.deg_2_pix(target_size)

        # prepare the pursuit target, the clock and the movement parameters
        self.win.color = [0, 0, 0]
        self.win.flip()
        self.target = visual.GratingStim(
            self.win, tex=None, mask="circle", size=self.target_size_pix
        )

    def pos_psych2pix(self, locs: list):
        """compute location x, y from 0 centered psychopy to top-left centered pixels"""
        x = int(locs[0] + self.win.size[0] / 2.0)
        y = int(self.win.size[1] / 2.0 - locs[1])
        return [x, y]

    def send_target_loc(
            self, loc: list, target_name="target", to_marker=True, no_interpolation=0
    ):
        """send target loc(ation) 0 centered to eyetracker after converting to top-left centered pixels.
        no_interpolation: 0 or 1
            0 interpolates, 1 doesn't"""
        loc = self.pos_psych2pix(loc)
        self.sendMessage(
            f"!V TARGET_POS {target_name} {loc[0]}, {loc[1]} 1 {no_interpolation}",
            to_marker,
        )  # 1 0  eyetracker code x, y, draw (1 yes), interpolation (0 == yes)

    def deg_2_pix(self, deg):
        return deg2pix(deg, self.subj_screendist_cm, self.pixpercm)

    def sendMessage(self, msg, to_marker=True, add_event=False):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.sendMessage(msg)
            if to_marker:
                self.send_marker(msg, add_event)

    def setOfflineMode(self):
        if self.eye_tracker is not None:
            self.eye_tracker.paused = True
            self.eye_tracker.tk.setOfflineMode()

    def startRecording(self):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.startRecording(1, 1, 1, 1)
            self.eye_tracker.paused = False

    def sendCommand(self, msg):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.sendCommand(msg)

    def doDriftCorrect(self, vals):
        # vals : int, position target in screen
        if self.eye_tracker is not None:
            self.eye_tracker.tk.doDriftCorrect(*vals)

    def gaze_contingency(self):
        # move task
        pass


class Introduction_Task(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self, **kwargs):
        self.present_instructions(prompt=False)


if __name__ == "__main__":

    instruction_file = op.join(neurobooth_os.__path__[0], "tasks", "assets", "test.mp4")
    if not op.isfile(instruction_file):
        raise IOError(f'Required instruction file {instruction_file} does not exist.')

    task = Task_countdown(
        instruction_file=instruction_file
    )

    task.run(prompt=True, duration=3)
