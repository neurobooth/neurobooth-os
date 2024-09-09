import os
import json
from asyncio import sleep
from typing import Optional, Dict, List
from enum import IntEnum, auto
from concurrent.futures import ThreadPoolExecutor, wait

from neurobooth_os.msg.messages import StatusMessage, Request, ResetMbients, MbientResetResults
from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks.utils import get_keys
from psychopy import visual
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.mbient import Mbient


def send_reset_msg() -> Dict[str, bool]:
    """
    Send mbient reset message to ACQ and collect results

    Returns
    -------
    Reset results as dictionary
    """
    msg = ResetMbients()
    results = None
    attempts = 0
    with meta.get_database_connection() as conn:
        req = Request(source='mbient_reset', destination='ACQ', body=msg)
        meta.post_message(req, conn)
        while results is None and attempts <= 180:
            reply = meta.read_next_message(
                destination="STM", conn=conn, msg_type="MbientResetResults")
            if reply is not None:
                results = reply.results
                print(results)
            attempts = attempts + 1
            if attempts >= 600:
                print("No results message found for mbient reset after 10 minutes")
                # TODO: Make this timeout shorter
            sleep(1)
    return results


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
            continue_key: str = 'return',
            repeat_key: str = 'r',
            skip_key: str = 'q',
            end_screen: Optional[str] = None,
            **kwargs
    ):
        """
        :param mbients: Stream names and associated Mbient objects for STM Mbients
        :param continue_key: Which key will continue/complete the task.
        :param repeat_key: Which key will trigger a repeated Mbient reset after a successful reset has already occured.
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
            self.end_screen = visual.ImageStim(
                self.win,
                image=os.path.join(self.root_pckg, "tasks", "assets", end_screen),
                pos=(0, 0),
                units="deg",
            )

    def run(self, **kwarg):
        self.task_state: TaskState = TaskState.RESET_NO_SUCCESS
        self.update_message()  # Present Intro Screen

        while self.task_state != TaskState.END_SCREEN:
            if self.task_state == TaskState.RESET_NO_SUCCESS:
                self.task_state = self.present_reset_no_success()
            elif self.task_state == TaskState.RESET_POST_SUCCESS:
                self.task_state = self.present_reset_post_success()

        if self.show_end_screen:
            self.present_end_screen()

    def present_reset_no_success(self) -> TaskState:
        text = f'Mbient Reset: {self.continue_key.upper()} to trigger reset, {self.skip_key.upper()} to skip.'
        self.send_status_msg(text)

        keys = get_keys([self.continue_key, self.skip_key])
        if self.skip_key in keys:
            return TaskState.END_SCREEN
        elif self.continue_key in keys:
            return self.reset_mbient_wrapper()
        else:
            self.logger.error(f'Unreachable case! keys={keys}')
            return TaskState.RESET_NO_SUCCESS

    @staticmethod
    def send_status_msg(text):
        msg = StatusMessage(text=text)
        with meta.get_database_connection() as conn:
            req = Request(source='mbient_reset', destination='CTR', body=msg)
            meta.post_message(req, conn)

    def present_reset_post_success(self) -> TaskState:
        text = (f'Mbient Reset Successful: '
                f'{self.continue_key.upper()} to advance,'
                f' {self.repeat_key.upper()} to repeat reset.')
        self.send_status_msg(text)

        keys = get_keys([self.continue_key, self.skip_key, self.repeat_key])
        if (self.continue_key in keys) or (self.skip_key in keys):  # Also accept skip key for convenience
            return TaskState.END_SCREEN
        elif self.repeat_key in keys:
            return self.reset_mbient_wrapper()
        else:
            self.logger.error(f'Unreachable case! keys={keys}')
            return TaskState.RESET_POST_SUCCESS

    def reset_mbient_wrapper(self) -> TaskState:
        try:
            if self.reset_mbients():
                return TaskState.RESET_POST_SUCCESS
            else:
                return TaskState.RESET_NO_SUCCESS
        except MbientResetPauseError as e:
            self.logger.exception(e)
            self.send_status_msg('Error encountered during reset...')  # Send message to GUI terminal
            return TaskState.RESET_NO_SUCCESS

    def present_end_screen(self) -> None:
        self.end_screen.draw()
        self.win.flip()
        self.send_status_msg(f'Pause: Press {self.continue_key.upper()} to continue.')  # Send message to GUI terminal
        get_keys([self.continue_key])  # Wait until continue key is pressed

    def update_message(self, contents: List[str] = ()):
        """Update the message on the screen.
        :param contents: A list of messages to be displayed on separate lines.
        """
        message = '\n'.join([self.header_message, *contents])
        self._screen.text = message
        self._screen.draw()
        self.win.flip()

    def reset_mbients(self) -> bool:
        """Reset the Mbient devices and report their status to the screen.
        :returns: Whether all devices successfully reset and reconnected.
        """
        self.update_message(['Reset in progress...'])

        # Concurrently reset devices
        with ThreadPoolExecutor(max_workers=len(self.mbients) + 1) as executor:
            # Signal ACQ to reset its Mbients
            acq_results = executor.submit(send_reset_msg)

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
            print(results)

        all_success = all([connected for _, connected in results.items()])

        # Display the results
        results = {
            stream_name: 'CONNECTED' if connected else 'ERROR'
            for stream_name, connected in results.items()
        }
        self.update_message([f'{stream_name}: {status}' for stream_name, status in results.items()])
        for stream_name, status in results.items():
            print(f'{stream_name} is {status}')  # Send message to GUI terminal

        return all_success
