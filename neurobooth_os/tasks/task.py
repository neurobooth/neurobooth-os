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

    def present_countdown(self) -> None:
        """
        Overrides present_countdown to perform a countdown prior to present_task for my subclasses
        """
        self.countdown_to_stimulus()

    def present_task(self, duration=0, **kwargs):
        self.show_text(screen=self.task_screen, msg="Task", audio=None, wait_time=3)

    # TODO: Combine with task version to eliminate redundant code
    def present_repeat_instruction_option(self, show_continue_repeat_slide: bool) -> bool:
        """
        Present the option to repeat instructions before stimulus
        Parameters
        ----------
        show_continue_repeat_slide : bool   if true, show the subject a slide offering the option to repeat the
        instructions. Otherwise, do nothing
        """

        if show_continue_repeat_slide:
            return self.show_repeat_continue_option(
                screen=self.instruction_end_screen,
                msg="Intructions-continue-repeat",
                waitKeys=False,
            )

    def present_repeat_task_option(self, show_continue_repeat_slide: bool) -> bool:
        if show_continue_repeat_slide:
            return self.show_repeat_continue_option(
                screen=self.task_end_screen,
                msg="Task-continue-repeat",
                waitKeys=False,
            )
