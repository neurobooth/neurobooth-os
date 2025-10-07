# -*- coding: utf-8 -*-
"""
 A task is an operation or sequence of steps performed presented to a subject via Psychopy.
"""
from __future__ import absolute_import, division

import logging
import os.path as op
import time

import neurobooth_os
import neurobooth_os.config as cfg
import neurobooth_os.iout.metadator as meta

from typing import List, Optional

from psychopy import logging as psychopy_logging

from neurobooth_os.msg.messages import StatusMessage, Request
from neurobooth_os.tasks import utils
from neurobooth_os.log_manager import APP_LOG_NAME

from datetime import datetime
from psychopy import visual, event


psychopy_logging.console.setLevel(psychopy_logging.CRITICAL)


class TaskAborted(Exception):
    """Exception raised when the task is aborted."""
    pass


class Task:
    # Note: incorrect file paths passed to Psychopy may cause the python interpreter to crash without raising an error.
    # These file paths must be checked before passing and an appropriate error raised, and so they
    # are checked inline below.
    # We cannot check paths with pydantic when loading the params because the path strings there are partial.

    instruction_video = None
    instruction_file: Optional[str] = None,

    def __init__(
            self,
            instruction_file=None,
            marker_outlet=None,
            win=None,
            full_screen: bool = False,
            text_continue=utils.text_continue,
            text_practice_screen=utils.text_practice_screen,
            text_task=utils.text_task,
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
        self.full_screen = full_screen
        self.events = []

        self.advance_keys: List[str] = ['space']
        self.abort_keys: List[str] = ['q']
        if task_repeatable_by_subject:
            task_end_img = 'task_end.png'
            inst_end_task_img = 'inst_end_task.png'
            self.repeat_keys: List[str] = ['r', 'comma']
        else:
            # Note: By overriding repeat_keys, disabling a task repeats also disables instruction repeats!
            task_end_img = 'task_end_disabled.png'
            inst_end_task_img = 'inst_end_task_disabled.png'
            self.repeat_keys: List[str] = ['r']

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

        self.instruction_file = instruction_file

        # Create mouse and set not visible
        self.Mouse = event.Mouse(visible=False, win=self.win)
        self.Mouse.setVisible(0)

        self.root_pckg = neurobooth_os.__path__[0]

        self.press_inst_screen = utils.load_slide(self.win, inst_end_task_img)
        self.press_task_screen = utils.load_slide(self.win, task_end_img)

        if countdown is None:
            countdown = "countdown_2025_06_17.mp4"
        self.countdown_video = utils.load_countdown(self.win, countdown)

        self.continue_screen = utils.create_text_screen(self.win, text_continue)
        self.practice_screen = utils.create_text_screen(self.win, text_practice_screen)
        self.task_screen = utils.create_text_screen(self.win, text_task)
        self.end_screen = utils.get_end_screen(self.win)

    def _load_instruction_video(self):
        """
        Loads instruction video if not previously loaded or if previously loaded but currently stopped.
        Returns
        -------

        """
        if self.instruction_file is not None:
            video = self.instruction_video
            if video is None or video.status == "STOPPED":
                path_instruction_video = op.join(
                    cfg.neurobooth_config.video_task_dir, self.instruction_file
                )
                self.instruction_video = visual.MovieStim3(
                    win=self.win, filename=path_instruction_video, noAudio=False
                )
        else:
            self.instruction_video = None

    def render_image(self):
        """
           Dummy method which does nothing.

           Tasks which need to render an image on HostPC/Tablet screen, need to
           render image before the eyetracker starts recording. This is done via
           calling the render_image method inside start_acq in server_stm.py
           This dummy method gets called for all tasks which don't need to send
           an image to HostPC screen.

           For tasks which do need to send an image to screen, a render_image
           method must be implemented inside the task script which will get called
           instead.
        """
        pass

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
            self._add_event(msg)

    def _add_event(self, event_name):
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
            abort_keys=None,
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
            abort_keys=abort_keys,
        )
        self.send_marker(f"{msg}_end", True)

        if func is not None:
            if self.repeat_advance():
                func(**func_kwargs)

    def _show_video(self, video, msg, stop=False):
        self.send_marker(f"{msg}_start", True)
        if video is not None:
            utils.play_video(self.win, video, stop=stop)
        self.send_marker(f"{msg}_end", True)

    def countdown_to_stimulus(self):
        """
        Displays countdown video prior to the start of stimulus
        """
        utils.play_video(self.win, self.countdown_video, wait_time=4, stop=False)
        utils.play_tone()

    def present_instructions(self, prompt=True):
        self._load_instruction_video()
        self._show_video(video=self.instruction_video, msg="Intructions")
        if prompt:
            self.show_text(
                screen=self.press_inst_screen,
                msg="Intructions-continue-repeat",
                func=self.present_instructions,
                waitKeys=False,
            )

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.countdown_to_stimulus()
        self.show_text(screen=self.task_screen, msg="Task", audio=None, wait_time=3)
        if prompt:
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                waitKeys=False,
            )

    def present_complete(self):
        screen = self.end_screen
        self.show_text(
            screen=screen, msg="Completed-task", audio=None, wait_time=0, waitKeys=False
        )
        self._close()

    # Close videos and win if just created for the task
    def _close(self):
        if self.instruction_video is not None:
            self.instruction_video.stop()
        self.countdown_video.stop()
        if self.win_temp:
            self.win.close()

    def present_practice(self, subj_id=None):
        pass

    def run(self, prompt=True, duration=0, subj_id=None, **kwargs):
        self.present_instructions(prompt)
        event.clearEvents(eventType='keyboard')
        self.present_practice(subj_id)
        event.clearEvents(eventType='keyboard')
        self.present_task(prompt=prompt, duration=duration, **kwargs)
        event.clearEvents(eventType='keyboard')
        self.present_complete()
        event.clearEvents(eventType='keyboard')
        return self.events

    def check_if_aborted(self) -> None:
        """Check to see if a task has been aborted. If so, raise an exception."""
        # TODO: add Task aborted message to appropriate places in utils
        if event.getKeys(keyList=self.abort_keys):
            with meta.get_database_connection() as db_conn:
                msg = StatusMessage(text="Task aborted")
                req = Request(source="STM", destination="CTR", body=msg)
                meta.post_message(req, db_conn)
            raise TaskAborted()
