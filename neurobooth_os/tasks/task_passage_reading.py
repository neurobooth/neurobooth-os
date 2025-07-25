# -*- coding: utf-8 -*-
"""
Created on Tue Nov 2 15:23:01 2021

Author: adonay Nunes <adonay.s.nunes@gmail.com>

License: BSD-3-Clause
"""

import os
import os.path as op
from typing import Union

from neurobooth_os.tasks.task import Eyelink_HostPC
from neurobooth_os.tasks import utils
from neurobooth_os.iout.stim_param_reader import get_cfg_path


class Passage_Reading(Eyelink_HostPC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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
            Passage_Reading.asset_path('bamboo_screenshot.jpg'),
            0, 0, 1920, 1080, 0, 0
        )

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.Mouse.setVisible(1)  # Allow participants to use the mouse to assist their reading
        screen = utils.load_image(self.win, Passage_Reading.asset_path('passage_reading_1536x864.jpg'))
        self.show_text(screen=screen, msg="Task", audio=None, wait_time=5)

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