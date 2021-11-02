# -*- coding: utf-8 -*-
"""
Created on Tue Nov 2 15:23:01 2021

Author: adonay Nunes <adonay.s.nunes@gmail.com>

License: BSD-3-Clause
"""

import os.path as op

from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks import utils
import neurobooth_os

class Passage_Reading(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def present_task(self, prompt=True):
        fname = op.join(neurobooth_os.__path__[0], 'tasks/assets/passage_reading_1536x864.jpg')
        screen = utils.create_image_screen(self.win, fname)
        self.present_text(screen=screen, msg='task', audio=None, wait_time=5)
        
        if prompt:
            self.present_text(screen=self.continue_repeat_screen, msg='continue-repeat', func=self.present_task,
                            waitKeys=False)   