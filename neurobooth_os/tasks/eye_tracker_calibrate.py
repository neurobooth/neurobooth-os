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
        if instructions:
            self.present_instructions(prompt)

        fname = self.eye_tracker.filename

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


if __name__ == "__main__":
    from neurobooth_os.iout.eyelink_tracker import EyeTracker
    from neurobooth_os.tasks import utils

    win = utils.make_win(False)
    eye_tracker = EyeTracker(win=win, ip="192.168.100.15")
    config.load_config()
    server_config = config.neurobooth_config.current_server()
    file_name = f"{server_config.local_data_dir}calibration.edf"
    cal = Calibrate(eye_tracker=eye_tracker, win=win, fname=file_name)
    cal.run()
    cal.win.close()
