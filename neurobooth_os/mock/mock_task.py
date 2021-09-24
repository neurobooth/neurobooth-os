
import sys
from neurobooth_os.tasks.utils import make_win
import neurobooth_os.tasks.utils as utl
import time

import os
import os.path as op



class simulated_task():
    def __init__(
            self,
            ntrials= 20,
            marker_outlet=None,
            win=None, 
            instruction_text,
            some_json_parameters,
            **kwarg):




        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
            # self.marker.push_sample([f"Streaming_0_{time.time()}"])
        else:
            self.with_lsl = False

        if win is None:
            full_screen = False

            # Setup the Window
            self.win = make_win(full_screen)
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False

        self.win.color = [0, 0, 0]
        self.win.flip()
        self.run()

    def send_marker(self, msg=None):
        # msg format str {word}_{value}
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])

    def run(self):

        print(instruction_text)
        sleep(1)

        for ntrials:
            self.send_marker(self, msg=None)
            sleep(self.duration/self.ntrials)