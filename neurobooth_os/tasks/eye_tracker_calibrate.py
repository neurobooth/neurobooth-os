# -*- coding: utf-8 -*-
"""
Created on Tue Nov 2 11:03:01 2021

Author: adonay Nunes <adonay.s.nunes@gmail.com>

License: BSD-3-Clause
"""
import os.path as op

from neurobooth_os.iout.metadator import post_message, get_database_connection
from neurobooth_os.msg.messages import NewVideoFile, Request
from neurobooth_os.tasks.task import Task_Eyetracker
from neurobooth_os import config


class Calibrate(Task_Eyetracker):
    def __init__(self, **kwargs):

        super().__init__(**kwargs)

    def run(self, prompt=True, instructions=True, **kwargs):
        fname = kwargs['fname']
        if instructions:
            self.present_instructions(prompt)

        body = NewVideoFile(stream_name=self.eye_tracker.streamName, filename=op.split(fname)[-1])
        msg = Request(source="EyeTracker", destination="CTR", body=body)
        post_message(msg, get_database_connection())

        self.fname = fname
        self.fname_temp = "name8chr.edf"
        self.eye_tracker.tk.openDataFile(self.fname_temp)

        self.eye_tracker.calibrate()

        # record for an instant so loadable in data viewer
        self.eye_tracker.tk.startRecording(1, 1, 1, 1)
        self.eye_tracker.tk.stopRecording()
        self.eye_tracker.tk.closeDataFile()
        # Download file
        self.eye_tracker.tk.receiveDataFile(self.fname_temp, self.fname)

        self.present_complete()
