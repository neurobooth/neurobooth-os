from __future__ import division, absolute_import

from neurobooth_os.tasks import utils
from neurobooth_os.tasks.task_basic import BasicTask


class Task_pause(BasicTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.slide_image = "end_slide_01_23_25.jpg"
        self.wait_key = kwargs['wait_key']
        self.screen = None

    def present_task(self, **kwarg):
        if self.wait_key is None:
            raise Exception("self.wait_key is none")
        else:
            print(f"wait_key = {self.wait_key}")
        self.screen = utils.load_slide(self.win, self.slide_image)
        self.screen.draw()
        self.win.flip()
        utils.get_keys(keyList=[self.wait_key])
        self.win.flip()


