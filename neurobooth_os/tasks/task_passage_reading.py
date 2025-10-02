# -*- coding: utf-8 -*-
"""
task for passage reading and picture description
"""

import os
import os.path as op
from typing import Union

from neurobooth_os.tasks.task import Eyelink_HostPC
from neurobooth_os.tasks import utils
from neurobooth_os.iout.stim_param_reader import get_cfg_path
from psychopy import event


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
    
    def _update_screen(self, image_filename):
        # change screen color to grey
        self.win.color = (0, 0, 0)
        # draw image screen
        screen = utils.load_image(self.win, Passage_Reading.asset_path(image_filename))
        screen.draw()
        self.win.flip()
    
    def _show_text(self, msg, wait_time):
        """Passage Reading's version of show text to accomodate needs of picture description task"""
        # send task_start marker
        self.send_marker(f"{msg}_start", True)
        # show passage reading image
        self._update_screen(image_filename=self.image_to_render_on_HostPC)

        # capture key press while waiting
        event.clearEvents(eventType='keyboard')
        time_elapsed = 0
        while True:
            # delay loop for 10 ms
            utils.delay(0.01)
            time_elapsed = time_elapsed + 0.01
            
            # check time - if timer runs out...
            if time_elapsed > wait_time:
                # ...update screen with new image
                self._update_screen(image_filename=self.image_to_render_on_tablet)

            # get key press
            press = event.getKeys()
            # if continue key pressed at any time
            if any([k in self.advance_keys for k in press]):
                # break out of the loop
                break
        
        # send task end marker
        self.send_marker(f"{msg}_end", True)        

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.countdown_to_stimulus()
        self.Mouse.setVisible(1)  # Allow participants to use the mouse to assist their reading
        self._show_text(msg="Task", wait_time=duration)

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
