from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC
from neurobooth_os.tasks.utils import load_video
import neurobooth_os.config as cfg
from os import path as op
import sys

import logging


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

    def present_instructions(self):
        try:
            super().present_instructions()
        except Exception as argument:
            from neurobooth_os.log_manager import make_db_logger
            logger = make_db_logger()  # Initialize logging to default
            logger.critical(f"An uncaught exception occurred presenting instructions. Exiting. Uncaught exception was: {repr(argument)}",
                            exc_info=sys.exc_info())
            raise argument
        finally:
            logging.shutdown()

    def present_stimulus(self, duration, **kwargs):
        try:
            path_video = op.join(
                cfg.neurobooth_config.video_task_dir, self.video_file
            )

            video = load_video(self.win, path_video)
            self._show_video(video=video, msg="Task")

        except Exception as argument:
            from neurobooth_os.log_manager import make_db_logger
            logger = make_db_logger()  # Initialize logging to default
            logger.critical(f"An uncaught exception occurred presenting stimulus. Exiting. Uncaught exception was: {repr(argument)}",
                            exc_info=sys.exc_info())
            raise argument
        finally:
            logging.shutdown()
