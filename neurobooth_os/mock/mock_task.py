
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
    instruction_text : str
        The instruction text.
    marker_outlet : instance of LSL Outlet
        The LSL stream sending the markers from STM computer.

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
        
        self.instruction_text = instruction_text

        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
        else:
            self.with_lsl = False

    def send_marker(self, msg=None):
        # msg format str {word}_{value}_{timestamp}
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])

    
    def run(self, n_trial=20, duration=10):
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

        # Run mock instructions
        self.send_marker("Intructions-start_0")
        print(self.instruction_text)
        time.sleep(1)
        self.send_marker("Intructions-end_1")
       
       # Run mock trials
        self.send_marker("Task-start_0")
        for _ in range(self.n_trials):
            self.send_marker(msg=f"Trial-start_0")
            time.sleep(self.duration/self.ntrials)
            self.send_marker(msg=f"Trial-end_1")
        self.send_marker("Task-end_1")

        print("Mock task finished!")