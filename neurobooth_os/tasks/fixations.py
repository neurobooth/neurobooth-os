# -*- coding: utf-8 -*-
"""

"""

from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC
from neurobooth_os.tasks import utils, Task_Eyetracker


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
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                func_kwargs=func_kwargs,
                waitKeys=False,
            )


class Fixation_Target_Multiple(Eyelink_HostPC):
    """
    Fixation task with multiple targets. Each target is presented alone, sequentially and each is
    treated as an individual trial
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(
        self,
        prompt=True,
        duration=3,
        trial_pos=[(0, 0), (0, 15)],
        target_size=0.7,
        **kwargs
    ):

        self.sendMessage(self.marker_task_start)
        self.countdown_to_stimulus()

        for pos in trial_pos:
            self.target.pos = [self.deg_2_pix(pos[0]), self.deg_2_pix(pos[1])]
            self.target.size = self.deg_2_pix(target_size)  # target_size from deg to cms
            if sum(self.target.size):
                self.send_target_loc(self.target.pos)

            # Send event to eyetracker and to LSL separately
            self.sendMessage(self.marker_trial_start, False)
            self.update_screen(self.target.pos[0], self.target.pos[1])
            self.show_text(
                screen=self.target,
                msg="Trial",
                audio=None,
                wait_time=duration,
                waitKeys=False,
            )
            self.sendMessage(self.marker_trial_end, False)

        self.sendMessage(self.marker_task_end)
        self.clear_screen()

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

    t = Fixation_Target_Multiple()
    t.run(duration=3, trial_pos=[(0, 7.5), (15, 7.5), (-15, 0)], target_size=0.7)
