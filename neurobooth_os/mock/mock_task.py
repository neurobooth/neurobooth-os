
import sys
from neurobooth_os.tasks.utils import make_win
import neurobooth_os.tasks.utils as utl
import time

import os
import os.path as op


class MockTask():
    """Create mock task.

    Parameters
    ----------
    n_trials : int
        The number of trials.
    marker_outlet : instance of LSL Outlet
        The LSL stream sending the markers from STM computer.
    instruction_text : str
        The instruction text.

    Attributes
    ----------
    with_lsl : bool
        Should the markers be sent?
    marker : instance of LSL Outlet.
        The LSL stream sending the markers.
    """
    def __init__(
            self,
            instruction_text,
            marker_outlet=None
        ):
        
        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
        else:
            self.with_lsl = False

    def send_marker(self, msg=None):
        # msg format str {word}_{value}
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])

    def run(self, n_trial=20, duration=60, instruction_text=None):
        """Run the task.

        Parameters
        ----------
        n_trials : int
            The trials
        duration : float
            The duration
        instruction_text : str
            The path to the instruction file.
        """
        print(instruction_text)
 
        sleep(1)

        for n_trials:
            self.send_marker(self, msg=None)
            sleep(self.duration/self.ntrials)