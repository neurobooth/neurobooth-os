# -*- coding: utf-8 -*-
"""
 A task is an operation or sequence of steps performed presented to a subject via Psychopy.
"""
from __future__ import absolute_import, division

import neurobooth_os
import neurobooth_os.iout.metadator as meta

from psychopy import logging as psychopy_logging

from neurobooth_os.msg.messages import StatusMessage, Request
from neurobooth_os.tasks import utils
from neurobooth_os.tasks.task_basic import BasicTask, TaskAborted

from psychopy import event

psychopy_logging.console.setLevel(psychopy_logging.CRITICAL)


class Task(BasicTask):

    def __init__(
            self,
            text_continue=utils.text_continue,
            text_practice_screen=utils.text_practice_screen,
            text_task=utils.text_task,
            **kwargs,
    ):
        super().__init__()

        # Common markers
        self.marker_task_start = "Task_start"
        self.marker_task_end = "Task_end"
        self.marker_trial_start = "Trial_start"
        self.marker_trial_end = "Trial_end"
        self.marker_practice_trial_start = "PracticeTrial_start"
        self.marker_practice_trial_end = "PracticeTrial_end"
        self.marker_response_start = "Response_start"
        self.marker_response_end = "Response_end"

        # Create mouse and set not visible
        self.Mouse = event.Mouse(visible=False, win=self.win)
        self.Mouse.setVisible(0)

        self.root_pckg = neurobooth_os.__path__[0]

        self.continue_screen = utils.create_text_screen(self.win, text_continue)
        self.practice_screen = utils.create_text_screen(self.win, text_practice_screen)
        self.task_screen = utils.create_text_screen(self.win, text_task)

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

    def present_instructions(self, prompt: bool = True):
        """
        Present instructions before stimulus
        Parameters
        ----------
        prompt : bool
        """
        self._load_instruction_video()
        self._show_video(video=self.instruction_video, msg="Intructions")
        if prompt:
            self.show_text(
                screen=self.instruction_end_screen,
                msg="Intructions-continue-repeat",
                func=self.present_instructions,
                waitKeys=False,
            )

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.countdown_to_stimulus()
        self.show_text(screen=self.task_screen, msg="Task", audio=None, wait_time=3)
        if prompt:
            self.show_text(
                screen=self.task_end_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                waitKeys=False,
            )

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
