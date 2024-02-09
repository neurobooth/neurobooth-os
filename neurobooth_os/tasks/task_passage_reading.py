# -*- coding: utf-8 -*-
"""
Created on Tue Nov 2 15:23:01 2021

Author: adonay Nunes <adonay.s.nunes@gmail.com>

License: BSD-3-Clause
"""

import os.path as op

# from neurobooth_os.tasks.task import Task_Eyetracker
from neurobooth_os.tasks.task import Eyelink_HostPC
from neurobooth_os.tasks.task import EyelinkColor
from neurobooth_os.tasks import utils
import neurobooth_os


class Passage_Reading(Eyelink_HostPC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(self, prompt=True, duration=0, **kwargs):
        
        def _update_tablet_screen_with_passage():
            self.draw_box(int(self.SCN_W/2), int(self.SCN_H/2), 1536, 864, EyelinkColor.LIGHTRED)
        
        fname = op.join(
            neurobooth_os.__path__[0], "tasks/assets/passage_reading_1536x864.jpg"
        )
        screen = utils.create_image_screen(self.win, fname)
        _update_tablet_screen_with_passage()
        self.show_text(screen=screen, msg="Task", audio=None, wait_time=5)

        if prompt:
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                waitKeys=False,
            )
        
        self.clear_screen()

if __name__ == "__main__":

    task = Passage_Reading()
    task.run(prompt=True, duration=10)