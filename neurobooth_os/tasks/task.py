# -*- coding: utf-8 -*-
"""
 A task is an operation or sequence of steps performed presented to a subject via Psychopy.
"""
from __future__ import absolute_import, division

import neurobooth_os

from psychopy import logging as psychopy_logging

from neurobooth_os.tasks import utils
from neurobooth_os.tasks.task_instruction import InstructionTask

from psychopy import event

psychopy_logging.console.setLevel(psychopy_logging.CRITICAL)


class Task(InstructionTask):

    def __init__(
            self,
            text_continue=utils.text_continue,
            text_practice_screen=utils.text_practice_screen,
            text_task=utils.text_task,
            **kwargs,
    ):
        super().__init__(**kwargs)

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
