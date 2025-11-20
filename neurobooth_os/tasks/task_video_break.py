from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC
from neurobooth_os.tasks.utils import load_video
import neurobooth_os.config as cfg
from os import path as op


class VideoBreak(Eyelink_HostPC):
    """
    Show the video following instructions slide and countdown. Not repeatable by subject
    """
    def __init__(
        self,
        **kwargs,
    ):
        self.video_file = kwargs['video_file']
        super().__init__(**kwargs)

    def present_stimulus(self, duration, **kwargs):

        path_video = op.join(
            cfg.neurobooth_config.video_task_dir, self.video_file
        )
        video = load_video(self.win, path_video)
        self._show_video(video=video, msg="Task")
