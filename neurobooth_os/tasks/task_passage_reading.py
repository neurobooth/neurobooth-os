# -*- coding: utf-8 -*-
"""
Task where subject is presented with a block of text to read
"""

import os
import os.path as op
from typing import Union

from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC
from neurobooth_os.tasks import utils
from neurobooth_os.iout.stim_param_reader import get_cfg_path


class Passage_Reading(Eyelink_HostPC):
    def __init__(self, image_to_render_on_tablet, image_to_render_on_HostPC, **kwargs):
        super().__init__(**kwargs)
        self.image_to_render_on_tablet = image_to_render_on_tablet
        self.image_to_render_on_HostPC = image_to_render_on_HostPC

    @classmethod
    def asset_path(cls, asset: Union[str, os.PathLike]) -> str:
        """
        Get the path to the specified asset.
        :param asset: The name of the asset/file.
        :return: The file system path to the asset in the config folder.
        """
        return op.join(get_cfg_path('assets'), 'passage_reading', asset)

    def render_image(self):
        self._render_image(
            Passage_Reading.asset_path(self.image_to_render_on_tablet),
            0, 0, 1920, 1080, 0, 0
        )

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.countdown_to_stimulus()
        self.Mouse.setVisible(1)  # Allow participants to use the mouse to assist their reading
        screen = utils.load_image(self.win, Passage_Reading.asset_path(self.image_to_render_on_HostPC))
        self.show_text(screen=screen, msg="Task", audio=None, wait_time=duration)

        if prompt:
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                waitKeys=False,
            )

        self.clear_screen()


if __name__ == "__main__":
    task = Passage_Reading()
    task.run(prompt=True, duration=10)
