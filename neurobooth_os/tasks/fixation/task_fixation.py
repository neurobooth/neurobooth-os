# -*- coding: utf-8 -*-
"""

"""
from neurobooth_os.tasks import Task_Eyetracker


class Fixation_Target(Task_Eyetracker):
    """
    Fixation tasks with zero or one visible target
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(
        self, prompt=True, duration=3, target_pos=(-10, 5), target_size=0.7, **kwargs
    ):
        self.countdown_to_stimulus()
        self.target.pos = [self.deg_2_pix(target_pos[0]), self.deg_2_pix(target_pos[1])]
        self.target.size = self.deg_2_pix(target_size)  # target_size from deg to cms
        if sum(self.target.size):
            self.send_target_loc(self.target.pos)

        # Send event to eyetracker and to LSL separately
        self.sendMessage(self.marker_task_start, False)
        self.show_text(
            screen=self.target,
            msg="Task",
            audio=None,
            wait_time=duration,
            waitKeys=False,
        )
        self.sendMessage(self.marker_task_end, False)

        if prompt:
            func_kwargs = locals()
            del func_kwargs["self"]
            self.show_text(
                screen=self.task_end_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                func_kwargs=func_kwargs,
                waitKeys=False,
            )
