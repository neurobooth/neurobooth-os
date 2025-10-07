from __future__ import division, absolute_import

from neurobooth_os.tasks import Task, utils


class Task_pause(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.screen = None

    def run(self, slide_image="end_slide_01_23_25.jpg", wait_key="return", **kwarg):
        self.screen = utils.load_slide(self.win, slide_image)
        self.screen.draw()
        self.win.flip()
        utils.get_keys(keyList=[wait_key])
        self.win.flip()
