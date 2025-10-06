from __future__ import division, absolute_import

from pylsl import local_clock

import neurobooth_os
from neurobooth_os.tasks import Task, utils
from neurobooth_os.tasks.task import TaskAborted

import os.path as op


class Task_countdown(Task):
    """
        Task whose instances are experiments that run for a fixed amount of time (counting down in seconds).
        It's used by speech tasks like 'La-La-La'
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(self, prompt, duration, **kwargs):
        self.countdown_to_stimulus()

        self.send_marker(self.marker_task_start, True)
        utils.present(self.win, self.task_screen, waitKeys=False)

        duration += 2  # No idea why, but the original code was like this...
        try:  # Keep presenting the screen until the task is over or the task is aborted.
            start_time = local_clock()
            while (local_clock() - start_time) < duration:
                self.check_if_aborted()
        except TaskAborted:
            self.logger.info('Task aborted.')

        self.win.flip()
        self.send_marker(self.marker_task_end, True)

        if prompt:
            func_kwargs = locals()
            del func_kwargs["self"]
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                func_kwargs=func_kwargs,
                waitKeys=False,
            )


if __name__ == "__main__":

    instruction_file = op.join(neurobooth_os.__path__[0], "tasks", "assets", "test.mp4")
    if not op.isfile(instruction_file):
        raise IOError(f'Required instruction file {instruction_file} does not exist.')

    task = Task_countdown(
        instruction_file=instruction_file
    )

    task.run(prompt=True, duration=3)
