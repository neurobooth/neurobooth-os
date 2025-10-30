from __future__ import division, absolute_import

from pylsl import local_clock

from neurobooth_os.tasks import Task, utils
from neurobooth_os.tasks.task_basic import TaskAborted


class Task_countdown(Task):
    """
        Task whose instances are experiments that run for a fixed amount of time (counting down in seconds).
        It's used by speech tasks like 'La-La-La'
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(self, show_continue_repeat_slide, duration, **kwargs):

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

        if show_continue_repeat_slide:
            func_kwargs = locals()
            del func_kwargs["self"]
            self.show_text(
                screen=self.task_end_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                func_kwargs=func_kwargs,
                waitKeys=False,
            )
