# -*- coding: utf-8 -*-
"""
Created on Thu Oct 14 11:03:01 2021

Author: Sheraz Khan <sheraz@khansheraz.com>

License: BSD-3-Clause
"""

from __future__ import absolute_import, division
from psychopy import logging as psychopy_logging

psychopy_logging.console.setLevel(psychopy_logging.CRITICAL)
import logging
import os.path as op
from datetime import datetime
import time

from psychopy import visual, monitors, sound, core, event
from psychopy import prefs

import neurobooth_os
from neurobooth_os.tasks import utils
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix
from neurobooth_os.log_manager import APP_LOG_NAME

from enum import Enum


class Task:
    def __init__(
            self,
            instruction_file=None,
            marker_outlet=None,
            win=None,
            full_screen=False,
            text_continue_repeat=utils.text_continue_repeat,
            text_continue=utils.text_continue,
            text_practice_screen=utils.text_practice_screen,
            text_task=utils.text_task,
            text_end=utils.text_end,
            countdown=None,
            task_repeatable_by_subject=True,
            **kwargs,
    ):
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
        #         self.marker_trial_start_Nth = 'Trial_start_{}'
        #         self.marker_trial_end_Nth = 'Trial_end_{}'

        # self.path_instruction_video = op.join(cfg.neurobooth_config['video_tasks'], instruction_file)
        self.task_files = None
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

        if self.path_instruction_video:
            print(f"Loading {self.path_instruction_video}")

        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet

        else:
            self.with_lsl = False

        if win is None:
            # Setup the Window
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

        self.press_inst_screen = visual.ImageStim(
            self.win,
            image=op.join(self.root_pckg, "tasks/assets/inst_end_task.png"),
            pos=(0, 0),
            units="deg",
        )

        self.press_task_screen = visual.ImageStim(
            self.win,
            image=op.join(self.root_pckg, task_end_image),
            pos=(0, 0),
            units="deg",
        )
        if countdown is None:
            countdown = "countdown_2021_11_22.mp4"
        self.countdown_video = visual.MovieStim3(
            win=self.win,
            filename=op.join(neurobooth_os.__path__[0], "tasks", "assets", countdown),
            noAudio=False,
        )

        self.continue_screen = utils.create_text_screen(self.win, text_continue)
        self.practice_screen = utils.create_text_screen(self.win, text_practice_screen)
        self.task_screen = utils.create_text_screen(self.win, text_task)
        self.end_screen = visual.ImageStim(
            self.win,
            image=op.join(self.root_pckg, "tasks/assets/task_complete.png"),
            pos=(0, 0),
            units="deg",
        )
        self.end_tasks = visual.ImageStim(
            self.win,
            image=op.join(self.root_pckg, "tasks/assets/end_slide_3_7_22.png"),
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
            func_kwargs={},
            audio=None,
            wait_time=0,
            win_color=(0, 0, 0),
            waitKeys=True,
            first_screen=False,
    ):

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

    def run(self, slide_image="end_slide_3_7_22.jpg", wait_key="return", **kwargs):
        # slide_image : filename image in tasks/assets

        self.screen = visual.ImageStim(
            self.win,
            image=op.join(self.root_pckg, "tasks", "assets", slide_image),
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
            # params: file_sample, file_event, link_sampe, link_event (1-yes, 0-no)
            self.eye_tracker.tk.startRecording(1, 1, 1, 1)
            self.eye_tracker.paused = False

    def sendCommand(self, msg):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.sendCommand(msg)

    def doDriftCorrect(self, vals):
        # vals : int, position target in screen
        if self.eye_tracker is not None:
            self.eye_tracker.tk.doDriftCorrect(*vals)

    def gaze_contingency():
        # move task
        pass


class Color(Enum):
    BLACK = 0
    RED = 12
    GREEN = 10


class Eyelink_HostPC(Task_Eyetracker):
    '''
       Class containing methods that interact with the HostPC display.
       HostPC is the computer that controls the eye tracker camera. Tasks
       can interact with the display that is attached to this computer. In
       our set up, the display is an Android tablet running the Eyelink app.

       The commands that are sent to the HostPC are in the form of strings,
       the list of commands and documentation is available in the
       "commands.ini" file inside the HostPC (i.e. NUC) - this can be found 
       via the WebUI or by browsing the filesystem in the NUC. Additional
       documentation is in the SR Research forums.
    '''
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def draw_cross(self, x: int, y: int, colour: Color) -> None:
        '''Draw a cross at the x,y position on the screen of the specified colour
           x, y must be in the top-left centered coordinate space 
        '''
        self.sendCommand('draw_cross %d %d %d' % tuple(x, y, colour.value))
        
    def draw_box(self, x: int, y: int, length: int, breadth: int, colour: Color, filled: bool = False) -> None:
        '''
           Draw a rectangle of size length by breadth (in pixels) around a point 
           x,y on the screen. x, y must be in the top-left centered coordinate
           space.

           'draw_box' command for the HostPC takes in the diagonal coordinates and
           a color integer
        '''
        half_box_len_in_pix = int(length/2)
        half_box_brd_in_pix = int(breadth/2)

        box_coords_top_x = x-half_box_len_in_pix
        box_coords_top_y = y-half_box_brd_in_pix
        box_coords_bot_x = x+half_box_len_in_pix
        box_coords_bot_y = y+half_box_brd_in_pix

        if not filled:
            self.sendCommand('draw_box %d %d %d %d %d' % tuple(box_coords_top_x, box_coords_top_y,
                                                               box_coords_bot_x, box_coords_bot_y,
                                                               colour.value))
        else:
            # add command for filled box
            pass

    def update_screen(self, x: float, y: float) -> None:
        '''
           Draw a cross and a box on the eyelink tablet.
           x and y are positions in 0 centered psychopy coordinate space.
           x and y can be int or float
           See pos_psych2pix above
        '''

        # First clear tablet screen
        self.clear_screen()

        # convert from 0 centered to top-left centered coordinate space
        xy = self.pos_psych2pix([x, y])
        top_left_x = xy[0]
        top_left_y = xy[1]

        # draw cross at top_left centered x,y position
        self.draw_box(top_left_x, top_left_y, Color.GREEN)

        # draw box around cross
        box_len_in_pix = 100
        self.draw_box(top_left_x, top_left_y, box_len_in_pix, box_len_in_pix, Color.RED)

    def clear_screen(self, colour: Color = Color.BLACK) -> None:
        '''Clear the HostPC screen and leave a Black background by default'''
        self.sendCommand('clear_screen %d' % colour.value)


class Introduction_Task(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self, **kwargs):
        self.present_instructions(prompt=False)


if __name__ == "__main__":
    # task = Task(instruction_file=op.join(neurobooth_os.__path__[0], 'tasks', 'assets', 'test.mp4'))
    # task.run()

    task = Task_countdown(
        instruction_file=op.join(
            neurobooth_os.__path__[0], "tasks", "assets", "test.mp4"
        )
    )
    task.run(prompt=True, duration=3)
