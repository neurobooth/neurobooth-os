from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC
from neurobooth_os.tasks.utils import load_video


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
        video = load_video(self.win, self.video_file)
        self._show_video(video=video, msg="Task")
