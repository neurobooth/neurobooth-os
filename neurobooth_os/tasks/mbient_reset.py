import os
import json
from typing import Optional, Dict, List
from enum import IntEnum, auto
from concurrent.futures import ThreadPoolExecutor, wait
from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks.utils import get_keys
from psychopy import visual
from neurobooth_os.iout.mbient import Mbient
from neurobooth_os.netcomm import socket_message


class UserInputEvent(IntEnum):
    CONTINUE = auto()
    RESET = auto()


class MbientResetPauseError(Exception):
    pass


class MbientResetPause(Task):
    """Pause the session so that the Mbient wearables can be reset to improve data quality."""

    def __init__(
            self,
            mbients: Optional[Dict[str, Mbient]] = None,
            continue_key: str = 'return',
            reset_key: str = 'r',
            end_screen: Optional[str] = None,
            **kwargs
    ):
        """
        :param mbients: Stream names and associated Mbient objects for STM Mbients
        :param continue_key: Which key will continue/complete the task
        :param reset_key: Which kill will trigger a reset of the Mbients
        :param end_screen: If not None, present the specified image after the reset is complete
        :param kwargs: Keyword arguments to be passed on to the task constructor
        """
        super().__init__(**kwargs)
        self.mbients = mbients  # These are the mbients connected to STM
        self.continue_key = continue_key
        self.reset_key = reset_key
        self.text_size = 48
        self.header_message = "Please wait while we reset the wearable devices.\n"

        width, height = self.win.size
        self._screen = visual.TextStim(
            self.win,
            self.header_message,
            height=self.text_size,
            color=[1, 1, 1],
            pos=(0, 0),
            wrapWidth=width,
            units="pix",
        )

        self.show_end_screen = end_screen is not None
        if self.show_end_screen:
            self.end_screen = visual.ImageStim(
                self.win,
                image=os.path.join(self.root_pckg, "tasks", "assets", end_screen),
                pos=(0, 0),
                units="deg",
            )

    def run(self, **kwargs):
        # Send message to GUI terminal
        print(f'Mbient Reset: {self.reset_key.upper()} to trigger reset, {self.continue_key.upper()} to continue.')

        # Present Intro Screen
        self.update_message()

        try:  # Perform resets until the continue key is pressed
            event = self.wait_for_key()
            while event == UserInputEvent.RESET:
                self.reset_mbients()
                event = self.wait_for_key()
        except MbientResetPauseError as e:
            self.logger.exception(e)

        # Progress to the end screen
        if not self.show_end_screen:
            return

        self.end_screen.draw()
        self.win.flip()
        print(f'Pause: Press {self.continue_key.upper()} to continue.')  # Send message to GUI terminal
        get_keys([self.continue_key])  # Wait until continue key is pressed

    def wait_for_key(self) -> UserInputEvent:
        """Wait for a valid key input event.
        :returns: The type of detected event.
        """
        keys = get_keys(keyList=[self.continue_key, self.reset_key])
        if self.continue_key in keys:
            return UserInputEvent.CONTINUE
        elif self.reset_key in keys:
            return UserInputEvent.RESET
        else:
            raise MbientResetPauseError(f'Reached "impossible" case with keys: {keys}')

    def update_message(self, contents: List[str] = ()):
        """Update the message on the screen.
        :param contents: A list of messages to be displayed on separate lines.
        """
        message = '\n'.join([self.header_message, *contents])
        self._screen.text = message
        self._screen.draw()
        self.win.flip()

    def reset_mbients(self) -> None:
        """Reset the Mbient devices and report their status to the screen."""
        self.update_message(['Reset in progress...'])

        # Concurrently reset devices
        with ThreadPoolExecutor(max_workers=len(self.mbients)+1) as executor:
            # Signal ACQ to reset its Mbients
            acq_results = executor.submit(socket_message, 'reset_mbients', 'acquisition', wait_data=True)

            # Begin reset of local Mbients
            stm_results = {
                stream_name: executor.submit(stream.reset_and_reconnect)
                for stream_name, stream in self.mbients.items()
            }

            # Wait for all resets to complete, then resolve the futures
            wait([acq_results, *stm_results.values()])

            # Parse result from ACQ
            acq_results = acq_results.result()
            if acq_results is not None:
                acq_results = json.loads(acq_results)
            else:
                self.logger.warn('Received None response from ACQ reset_mbients.')
                acq_results = {}

            stm_results = {stream_name: result.result() for stream_name, result in stm_results.items()}

            # Combine results from all serves
            results = {**acq_results, **stm_results}

        # Display the results
        results = {
            stream_name: 'CONNECTED' if connected else 'ERROR'
            for stream_name, connected in results.items()
        }
        self.update_message([f'{stream_name}: {status}' for stream_name, status in results.items()])
        for stream_name, status in results.items():
            print(f'{stream_name} is {status}')  # Send message to GUI terminal
