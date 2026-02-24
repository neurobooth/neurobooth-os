from datetime import datetime
import time
from typing import Optional, Dict, List
from enum import IntEnum, auto
from neurobooth_os.msg.messages import StatusMessage, Request, ResetMbients
from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks.utils import get_keys, load_slide
from psychopy import visual
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.mbient import Mbient
from neurobooth_os import config


def _send_reset_msg() -> Dict[str, bool]:
    """
    Send mbient reset message to all ACQ servers and collect results.

    Returns
    -------
    Reset results as dictionary of mbient device names to booleans
    """
    acq_ids = config.neurobooth_config.all_acq_service_ids()
    all_results: Dict[str, bool] = {}

    minutes_to_wait = 5
    max_attempts = minutes_to_wait * 60
    attempts = 0

    with meta.get_database_connection() as conn:
        for acq_id in acq_ids:
            msg = ResetMbients()
            req = Request(source='mbient_reset', destination=acq_id, body=msg)
            meta.post_message(req, conn)

        replies = 0
        while replies < len(acq_ids) and attempts <= max_attempts:
            reply = meta.read_next_message(
                destination="STM", conn=conn, msg_type="MbientResetResults")
            if reply is not None:
                all_results.update(reply.body.results)
                replies += 1
            elif attempts >= max_attempts:
                txt = f"No results from mbient reset after {attempts} attempts at {datetime.now().time()}."
                meta.post_message(Request(body=StatusMessage(text=txt), source="mbient_reset", destination="CTR"), conn)
                break
            else:
                time.sleep(1)
                attempts += 1
    return all_results


class TaskState(IntEnum):
    RESET_NO_SUCCESS = auto()
    RESET_POST_SUCCESS = auto()
    END_SCREEN = auto()


class MbientResetPauseError(Exception):
    pass


class MbientResetPause(Task):
    """
    Pause the session so that the Mbient wearables can be reset to improve data quality.

    This pause-like task has three phases/states.
    These states ensure that pressing the continue key will always produce a reasonable default effect.
    1. RESET_NO_SUCCESS: The initial state. The continue key will trigger a reset. If the reset is successful, the state
        will advance to RESET_POST_SUCCESS. If the skip key is pressed instead, the state will advance to END_SCREEN
        without performing a reset.
    2. RESET_POST_SUCCESS: The continue key will advance to END_SCREEN without performing a reset. If a repeat is
        desired, the repeat key will advance to either RESET_NO_SUCCESS or RESET_POST_SUCCESS depending on whether the
        reset was successful.
    3. END_SCREEN: Simply wait for the continue key to be pressed.
    """

    def __init__(
            self,
            mbients: Optional[Dict[str, Mbient]] = None,
            continue_key: str = 'enter',
            repeat_key: str = 'r',
            skip_key: str = 'q',
            end_screen: Optional[str] = None,
            **kwargs
    ):
        """
        :param mbients: Stream names and associated Mbient objects for STM Mbients
        :param continue_key: Which key will continue/complete the task.
        :param repeat_key: Which key will trigger a repeated Mbient reset after a successful reset has already occurred.
        :param skip_key: Which key will skip the reset.
        :param end_screen: If not None, present the specified image after the reset is complete
        :param kwargs: Keyword arguments to be passed on to the task constructor
        """
        super().__init__(**kwargs)
        self.mbients = mbients  # These are the mbients connected to STM
        self.text_size = 48
        self.header_message = "Please wait while we reset the wearable devices.\n"

        self.task_state: TaskState = TaskState.RESET_NO_SUCCESS
        self.continue_key = continue_key
        self.repeat_key = repeat_key
        self.skip_key = skip_key

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
            self.end_screen = load_slide(self.win, end_screen)
        self.duration = kwargs['duration']

    def _continue_key_for_comparison(self):
        """ We want the UI to say 'ENTER', but the system calls the enter key 'return'"""
        if self.continue_key == 'enter':
            return 'return'
        return self.continue_key

    def run(self, **kwarg):
        self.task_state: TaskState = TaskState.RESET_NO_SUCCESS
        self._update_message()  # Present Intro Screen

        while self.task_state != TaskState.END_SCREEN:
            if self.task_state == TaskState.RESET_NO_SUCCESS:
                self.task_state = self._present_reset_no_success()
            elif self.task_state == TaskState.RESET_POST_SUCCESS:
                self.task_state = self._present_reset_post_success()

        if self.show_end_screen:
            self.present_end_screen()

    def _present_reset_no_success(self) -> TaskState:
        text = f'Mbient Reset: {self.continue_key.upper()} to trigger reset, {self.skip_key.upper()} to skip.'
        self._send_status_msg(text)

        keys = get_keys([self._continue_key_for_comparison(), self.skip_key])
        if self.skip_key in keys:
            return TaskState.END_SCREEN
        elif self._continue_key_for_comparison() in keys:
            return self._reset_mbient_wrapper()
        else:
            self.logger.error(f'Unreachable case! keys={keys}')
            return TaskState.RESET_NO_SUCCESS

    @staticmethod
    def _send_status_msg(text):
        msg = StatusMessage(text=text)
        with meta.get_database_connection() as conn:
            req = Request(source='mbient_reset', destination='CTR', body=msg)
            meta.post_message(req, conn)

    def _present_reset_post_success(self) -> TaskState:
        text = (f'Mbient Reset Successful: '
                f'{self.continue_key.upper()} to advance,'
                f' {self.repeat_key.upper()} to repeat reset.')
        self._send_status_msg(text)

        keys = get_keys([self._continue_key_for_comparison(), self.skip_key, self.repeat_key])
        if (self._continue_key_for_comparison() in keys) or (self.skip_key in keys):  # Also accept skip key for convenience
            return TaskState.END_SCREEN
        elif self.repeat_key in keys:
            return self._reset_mbient_wrapper()
        else:
            self.logger.error(f'Unreachable case! keys={keys}')
            return TaskState.RESET_POST_SUCCESS

    def _reset_mbient_wrapper(self) -> TaskState:
        try:
            if self._reset_mbients():
                return TaskState.RESET_POST_SUCCESS
            else:
                return TaskState.RESET_NO_SUCCESS
        except MbientResetPauseError as e:
            self.logger.exception(e)
            self._send_status_msg('Error encountered during reset...')  # Send message to GUI terminal
            return TaskState.RESET_NO_SUCCESS

    def present_end_screen(self) -> None:
        self.show_text(screen=self.end_screen, msg="Task", audio=None, wait_time=self.duration, waitKeys=False)

    def _update_message(self, contents: List[str] = ()):
        """Update the message on the STM screen.
        :param contents: A list of messages to be displayed on separate lines.
        """
        message = '\n'.join([self.header_message, *contents])
        self._screen.text = message
        self._screen.draw()
        self.win.flip()

    def _reset_mbients(self) -> bool:
        """Reset the Mbient devices and report their status to the screen.

        Sends reset messages to all ACQ servers (which now own all Mbient devices)
        and reports the results.

        Returns
        -------
        bool
            Whether all devices successfully reset and reconnected.
        """
        self._update_message(['Reset in progress...'])

        results = _send_reset_msg()

        all_success = all(connected for connected in results.values())

        # Display the results
        display_results = {
            stream_name: 'CONNECTED' if connected else 'ERROR'
            for stream_name, connected in results.items()
        }
        self._update_message([f'{stream_name}: {status}' for stream_name, status in display_results.items()])
        for stream_name, status in display_results.items():
            print(f'{stream_name} is {status}')  # Send message to GUI terminal

        return all_success
