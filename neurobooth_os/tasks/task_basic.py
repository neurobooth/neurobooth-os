from __future__ import division, absolute_import

import os
import time
from os import path as op
from typing import List, Optional, Union
from datetime import datetime

import logging
import os.path as op

from psychopy import visual, event

from neurobooth_os.iout.stim_param_reader import get_cfg_path
from neurobooth_os.tasks import utils
import neurobooth_os.config as cfg
from neurobooth_os.log_manager import APP_LOG_NAME


class TaskAborted(Exception):
    """Exception raised when the task is aborted."""
    pass


class BasicTask:
    """
    Skeletal Task implementation that doesn't do anything except implement a run method made up of
    steps that can be overridden in subclasses.

    Should never be instantiated directly

    Note: incorrect file paths passed to Psychopy may cause the python interpreter to crash without raising an error.
    These file paths must be checked before passing and an appropriate error raised, so they're checked inline
    below. We cannot check paths with pydantic when loading the params because the path strings there are partial.

    """

    instruction_video = None
    instruction_file: Optional[str] = None,

    def __init__(self,
                 instruction_file=None,
                 win=None,
                 marker_outlet=None,
                 full_screen: bool = False,
                 # TODO: Make every task config have an entry for countdown. None defaults to a video lower in code
                 countdown=None,
                 # TODO: Make instr_repeatable_by_subject a separate flag
                 # TODO: Make every task config have an entry for task_repeatable_by_subject
                 task_repeatable_by_subject: bool = True,
                 **kwargs):
        self.logger = logging.getLogger(APP_LOG_NAME)

        self.instruction_file = instruction_file

        self.full_screen = full_screen
        self.win = win
        if win is None:
            # Set up the Window
            self.win = utils.make_win(self.full_screen)
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False

        self.events = []

        self.end_screen = utils.load_inter_task_slide(self.win)

        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
        else:
            self.with_lsl = False

        if countdown is None:
            countdown = "countdown_2025_06_17.mp4"
        self.countdown_video = utils.load_countdown(self.win, countdown)

        self.advance_keys: List[str] = ['space']
        self.abort_keys: List[str] = ['q']

        if task_repeatable_by_subject:
            task_end_img = 'task_end.png'                   # slide that says 'repeat task or continue to next task'
            inst_end_task_img = 'inst_end_task.png'         # slice that says 'start task or repeat instructions'
            self.repeat_keys: List[str] = ['r', 'comma']
        else:
            # Note: By overriding repeat_keys, disabling a task repeats also disables instruction repeats!
            task_end_img = 'task_end_disabled.png'            # slide that says 'continue to next task' only.
            inst_end_task_img = 'inst_end_task_disabled.png'  # slide that says 'start task' only
            self.repeat_keys: List[str] = ['r']

        # slide that appears immediately after instructions
        self.instruction_end_screen = utils.load_slide(self.win, inst_end_task_img)

        # slide that appears immediately after task
        self.task_end_screen = utils.load_slide(self.win, task_end_img)

    def present_countdown(self):
        """TODO: Is this useful?"""
        pass

    def present_instructions(self, prompt):
        pass

    def present_practice(self, subj_id: str):
        pass

    def present_task(self, prompt, duration, **kwargs):
        pass

    def present_complete(self) -> None:
        """Presents a slide to subjects while they are waiting for the following task to start"""

        screen = self.end_screen
        self.show_text(
            screen=screen, msg="Completed-task", audio=None, wait_time=0, waitKeys=False
        )
        self._close()

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

    def _add_event(self, event_name):
        self.events.append(f"{event_name}:{datetime.now().strftime('%H:%M:%S')}")

    # Close videos and win if just created for the task
    def _close(self):
        if self.instruction_video is not None:
            self.instruction_video.stop()
        self.countdown_video.stop()
        if self.win_temp:
            self.win.close()

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

    @classmethod
    def asset_path(cls, asset: Union[str, os.PathLike], task_name: Optional[str] = '') -> str:
        """
        Get the path to the specified asset
        :param asset: The name of the asset/file
        :param task_name: identifier for the Task where this method is used, e.g. 'MOT'
        :return: The file system path to the asset in the config folder.
        """
        return op.join(get_cfg_path('assets'), task_name, asset)
