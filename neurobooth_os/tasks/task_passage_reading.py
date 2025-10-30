# -*- coding: utf-8 -*-
"""
Task where subject is presented with a block of text to read
"""

from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC
from neurobooth_os.tasks import utils, Task


class Passage_Reading(Eyelink_HostPC):
    def __init__(self, image_to_render_on_tablet, image_to_render_on_HostPC, **kwargs):
        super().__init__(**kwargs)
        self.image_to_render_on_tablet = image_to_render_on_tablet
        self.image_to_render_on_HostPC = image_to_render_on_HostPC

    def render_image(self):
        self._render_image(
            Task.asset_path(self.image_to_render_on_tablet, 'passage_reading'),
            0, 0, 1920, 1080, 0, 0
        )

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.Mouse.setVisible(1)  # Allow participants to use the mouse to assist their reading
        screen = utils.load_image(self.win, Task.asset_path(self.image_to_render_on_HostPC, 'passage_reading'))
        self.show_text(screen=screen, msg="Task", audio=None, wait_time=duration)

        if prompt:
            self.show_text(
                screen=self.task_end_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                waitKeys=False,
            )

        self.clear_screen()


if __name__ == "__main__":
    task = Passage_Reading()
    task.run(show_continue_repeat_slide=True, duration=10)
