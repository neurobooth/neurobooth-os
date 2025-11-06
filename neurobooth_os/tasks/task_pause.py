from __future__ import division, absolute_import

from neurobooth_os.tasks import utils
from neurobooth_os.tasks.task_basic import BasicTask


class Task_pause(BasicTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.slide_image = kwargs['slide_image']
        self.wait_key = kwargs['wait_key']
        self.screen = None

    def present_task(self, duration, **kwarg):
        self.screen = utils.load_slide(self.win, self.slide_image)
        self.screen.draw()
        self.win.flip()
        utils.get_keys(keyList=[self.wait_key])
        self.win.flip()


