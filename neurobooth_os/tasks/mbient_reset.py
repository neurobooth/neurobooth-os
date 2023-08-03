from typing import Optional, Dict
from enum import IntEnum, auto
from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks.utils import get_keys
from psychopy import visual
from neurobooth_os.iout.mbient import Mbient


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

        self._screen = visual.TextStim(
            self.win,
            "Please wait while we reset the wearable devices.",
            height=32,
            color=[1, 1, 1],
            pos=(0, (-self.win.size[1] / 2) + 32),
            wrapWidth=1920,
            units="pix",
        )

    def run(self, **kwargs):
        # Present Intro Screen
        self._screen.draw()
        self.win.flip()

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
            raise MbientResetPauseError(f'Reached "impossible" case with key={key}')

    def reset_mbients(self) -> None:
        pass
