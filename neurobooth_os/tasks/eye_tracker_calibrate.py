# -*- coding: utf-8 -*-
"""
Created on Tue Nov 2 11:03:01 2021

Author: adonay Nunes <adonay.s.nunes@gmail.com>

License: BSD-3-Clause
"""

from neurobooth_os.tasks.task import Task_Eyetracker


class Calibrate(Task_Eyetracker):
    def __init__(self, **kwargs):

        super().__init__(**kwargs)

    def run(self, prompt=True, fname="test", **kwargs):
            self.present_instructions(prompt)
            
            self.fname_temp = "name8chr.edf"
            self.tk.openDataFile(self.fname_temp)
            self.eye_tracker.calibrate()
            self.tk.closeDataFile()
            self.tk.receiveDataFile(self.fname_temp, fname)
            
            self.present_complete()
