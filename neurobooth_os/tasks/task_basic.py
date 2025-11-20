from __future__ import division, absolute_import

import os
import time
from os import path as op
from typing import List, Optional, Union
from datetime import datetime

import logging

from psychopy import event

from neurobooth_os.iout import metadator as meta
from neurobooth_os.iout.stim_param_reader import get_cfg_path
from neurobooth_os.msg.messages import StatusMessage, Request
from neurobooth_os.tasks import utils
import neurobooth_os.config as cfg
from neurobooth_os.log_manager import APP_LOG_NAME


class TaskAborted(Exception):
    """Exception raised when the task is aborted."""
    pass


# Clears keyboard events
def clear(evt):
    evt.clearEvents(eventType='keyboard')


class BasicTask:
    """
    Skeletal Task implementation that doesn't do anything except implement a run method made up of
    steps that can be overridden in subclasses.  See the run() method comment for details

    Should never be instantiated directly. Most tasks should subclass from Task, which provides real implementations for
    most of the steps.  Very simple tasks may subclass from here directly.

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
        self.task_files: List[str] = []

        self.full_screen = full_screen
        self.win = win

        if win is None:
            raise ValueError(f"No window provided in task {kwargs}")

        self.events = []

        self.end_screen = utils.load_inter_task_slide(self.win)

        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
        else:
            self.with_lsl = False

        # TODO: The countdown file should always be specified in the config. None should throw an exception if
        #   a countdown file is needed for the task
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
        """ Present a countdown video before the task starts """
        pass

    def present_instructions(self):
        """ Present instructions for the task. If the 'task' is strictly informational,
        this may be the only thing presented """
        pass

    def present_repeat_instruction_option(self, show_continue_repeat_slide: bool) -> bool:
        """
        Offer to repeat instructions if show_continue_repeat_slide is True
        """
        pass

    def present_practice(self, subj_id: str):
        """ Give the subject the opportunity to practice before beginning the stimuls """
        pass

    def present_stimulus(self, duration, **kwargs):
        """ Present the core task functionality for assessing subject performance """
        pass

    def present_repeat_task_option(self, show_continue_repeat_slide: bool) -> bool:
        """
        Offer to repeat the task beginning with the countdown if show_continue_repeat_slide is True
        """
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

    def _show_video(self, video, msg: str, stop=False) -> None:
        """
        Plays video, wrapping it in LSL start and end markers
        TODO: Why are markers sent even if the video is None?
        """
        self.send_marker(f"{msg}_start", True)
        if video is not None:
            utils.play_video(self.win, video, stop=stop)
        self.send_marker(f"{msg}_end", True)

    def _add_event(self, event_name):
        self.events.append(f"{event_name}:{datetime.now().strftime('%H:%M:%S')}")

    # Close videos and win if just created for the task
    def _close(self):
        if self.instruction_video is not None:
            self.instruction_video.stop()
        self.countdown_video.stop()

    def _load_instruction_video(self):
        """
        Loads instruction video if not previously loaded or if previously loaded but currently stopped.
        Returns
        -------

        """
        if self.instruction_file is not None:
            if self.instruction_video.status == "STOPPED":
                path_instruction_video = op.join(
                    cfg.neurobooth_config.video_task_dir, self.instruction_file
                )
                self.instruction_video = utils.load_video(win=self.win, path=path_instruction_video)

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

    def show_repeat_continue_option(
            self,
            screen,
            msg,
            audio=None,
            wait_time=0,
            win_color=(0, 0, 0),
            waitKeys=True,
            first_screen=False,
            abort_keys=None,
    ) -> bool:
        """
        Displays text and returns true if the task or instructions should be repeated

        Parameters
        ----------
        screen
        msg
        audio
        wait_time
        win_color
        waitKeys
        first_screen
        abort_keys

        Returns
        -------
        True if the task or instructions referenced in the displayed text should be repeated and False otherwise
        """
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
        return self.repeat_advance()

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

    # TODO: have separate prompts for repeating task and repeating instructions
    def run(self, show_continue_repeat_slide=True, duration=0, subj_id=None, **kwargs) -> None:
        """
        This method implements the standard structure for running a task. The steps are:
        - Presenting instructions
        - Offering the opportunity to repeat instructions
        - Presenting a practice phase
        - Presenting a countdown to the actual task start
        - Presenting the core task itself
        - Offering the opportunity to repeat the task, beginning with the countdown
        - Presenting a message that another task will follow

        In this class all the steps are implemented as separate functions. And they all have 'pass' implementations,
        except the last one. They should be overridden in subtasks as needed.

        For completely novel Tasks, the entire run method can be overridden

        Parameters
        ----------
        show_continue_repeat_slide  If true, the continue_repeat option is presented to subjects.
        duration    If the core task has a timeout, this is a positive integer, otherwise 0
        subj_id     The id of the subject
        kwargs      Any additional args.  # TODO: get rid of these and make the args explicit (to the degree possible)

        Returns     None
        -------

        """

        # Instruction phase (with potential repeat)
        while True:
            self.present_instructions()
            clear(event)
            repeat_instructions = self.present_repeat_instruction_option(show_continue_repeat_slide)
            if not repeat_instructions:
                break

        # Practice phase
        clear(event)
        self.present_practice(subj_id)

        # Core task phase (with potential repeat)
        clear(event)
        while True:
            self.present_countdown()
            clear(event)
            self.present_stimulus(duration=duration, **kwargs)
            clear(event)
            repeat_task = self.present_repeat_task_option(show_continue_repeat_slide)
            if not repeat_task:
                break
        clear(event)
        self.present_complete()
        clear(event)

    @classmethod
    def asset_path(cls, asset: Union[str, os.PathLike], task_name: Optional[str] = '') -> str:
        """
        Get the path to the specified asset
        :param asset: The name of the asset/file
        :param task_name: identifier for the Task where this method is used, e.g. 'MOT'
        :return: The file system path to the asset in the config folder.
        """
        return op.join(get_cfg_path('assets'), task_name, asset)

    def countdown_to_stimulus(self):
        """
        Displays countdown video prior to the start of stimulus
        """
        utils.play_video(self.win, self.countdown_video, wait_time=4, stop=False)
        utils.play_tone()

    def check_if_aborted(self) -> None:
        """Check to see if a task has been aborted. If so, raise an exception."""
        # TODO: add Task aborted message to appropriate places in utils
        if event.getKeys(keyList=self.abort_keys):
            with meta.get_database_connection() as db_conn:
                msg = StatusMessage(text="Task aborted")
                req = Request(source="STM", destination="CTR", body=msg)
                meta.post_message(req, db_conn)
            raise TaskAborted()
