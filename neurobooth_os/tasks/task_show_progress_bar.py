from __future__ import division, absolute_import

from neurobooth_os.tasks import TaskShell, utils


class Task_ShowProgressBar(TaskShell):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.screen = None

    def present_instructions(self, **kwargs) -> None:
        self.screen = utils.load_slide(self.win, kwargs['slide_image'])
        self.show_text(screen=self.screen, msg="Task", audio=None, wait_time=kwargs['duration'], waitKeys=kwargs['wait_keys'])
