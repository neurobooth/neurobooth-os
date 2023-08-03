from typing import Optional, Dict, List
from enum import IntEnum, auto
from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks.utils import get_keys
from psychopy import visual
from neurobooth_os.iout.mbient import Mbient
from neurobooth_os.netcomm import socket_message
import json


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
            **kwargs
    ):
        super().__init__(**kwargs)
        self.mbients = mbients  # TODO: Need some way to signal ACQ mbients to reset
        self.continue_key = continue_key
        self.reset_key = reset_key
        self.text_size = 48
        self.header_message = "Please wait while we reset the wearable devices."

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

    def run(self, **kwargs):
        print('Mbient Reset: R to trigger reset, ENTER to continue.')  # Send message to GUI terminal

        # Present Intro Screen
        self.update_message()

        try:  # Perform resets until the continue key is pressed
            event = self.wait_for_key()
            while event == UserInputEvent.RESET:
                self.reset_mbients()
                event = self.wait_for_key()
        except MbientResetPauseError as e:
            self.logger.exception(e)

        # Clean Up

    def wait_for_key(self) -> UserInputEvent:
        keys = get_keys(keyList=[self.continue_key, self.reset_key])
        if self.continue_key in keys:
            return UserInputEvent.CONTINUE
        elif self.reset_key in keys:
            return UserInputEvent.RESET
        else:
            raise MbientResetPauseError(f'Reached "impossible" case with keys: {keys}')

    def update_message(self, contents: List[str] = ()):
        message = '\n'.join([self.header_message, *contents])
        self._screen.text = message
        self._screen.draw()
        self.win.flip()

    def reset_mbients(self) -> None:
        self.update_message(['Reset in progress...'])

        # Reset ACQ devices
        acq_reset_results: str = socket_message('reset_mbients', 'acquisition', wait_data=True)
        acq_reset_results: Dict[str, bool] = json.loads(acq_reset_results)

        # Reset STM devices
        stm_reset_results = {
            stream_name: stream.reset_and_reconnect()
            for stream_name, stream in self.mbients.items()
        }

        # Combine and display results
        results = {**acq_reset_results, **stm_reset_results}
        results = {
            stream_name: 'CONNECTED' if connected else 'DISCONNECTED'
            for stream_name, connected in results.items()
        }
        self.update_message([f'{stream_name}: {status}' for stream_name, status in results.items()])
        for stream_name, status in results.items():
            print(f'{stream_name} is {status}')  # Send message to GUI terminal
