import logging
import os

from typing import Optional, Dict
from pydantic import BaseModel
from psycopg2.extensions import connection

from neurobooth_os import config
from neurobooth_os.iout.eyelink_tracker import EyeTracker
from neurobooth_os.iout.lsl_streamer import DeviceManager
from neurobooth_os.iout.metadator import build_tasks_for_collection
from neurobooth_os.log_manager import SystemResourceLogger
from neurobooth_os.tasks import utils as utl


class StmSession(BaseModel):
    """
    Holds data for the session that is initialized in the prepare stage and used in the present stage (or another stage)
    """

    session_name: str = ''
    collection_id: str
    logger: logging.Logger
    db_conn: connection
    win: Optional[object] = None
    session_folder: Optional[str] = None
    system_resource_logger: Optional[object] = None
    task_func_dict: Optional[Dict] = {}
    path: Optional[str] = None
    prompt: Optional[bool] = None
    device_manager: Optional[DeviceManager] = None
    eye_tracker: Optional[EyeTracker] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if kwargs["session_name"] is not None:
            self.session_name: str = kwargs["session_name"]
        self.collection_id = kwargs["collection_id"]
        self.db_conn = kwargs["db_conn"]
        self.logger = kwargs["logger"]
        self.session_folder = self.create_session_folder(self.logger, self.session_name)
        self.system_resource_logger: SystemResourceLogger = self.create_sys_resource_logger()
        self.task_func_dict = build_tasks_for_collection(self.collection_id)
        self.path = os.path.join(config.neurobooth_config.presentation.local_data_dir, self.session_name)
        self.win = self.init_window()

        # TODO(larry): This was set to true in 'present' phase, but get from stimulus obj?
        self.prompt = True

        self.device_manager = self.init_device_manager()
        self.eye_tracker = self.device_manager.get_eyelink_stream()

    @staticmethod
    def init_window():
        return utl.make_win(full_screen=config.neurobooth_config.fullscreen)

    def init_device_manager(self) -> DeviceManager:
        device_manager = DeviceManager(node_name='presentation')
        if device_manager.streams:
            device_manager.reconnect_streams()
        else:
            device_manager.create_streams(win=self.win, task_params=self.task_func_dict)
        return device_manager

    @staticmethod
    def create_session_folder(logger, session_name: str):
        ses_folder = os.path.join(config.neurobooth_config.presentation.local_data_dir, session_name)
        logger.info(f"Creating session folder: {ses_folder}")
        if not os.path.exists(ses_folder):
            os.mkdir(ses_folder)
        return ses_folder

    def create_sys_resource_logger(self):
        system_resource_logger = SystemResourceLogger('STM')
        system_resource_logger.start()
        return system_resource_logger

    def tasks(self):
        """Returns a list of tasks in the collection referenced by collection_id"""
        return self.task_func_dict.keys()

    def shutdown(self):
        if self.system_resource_logger is not None:
            self.system_resource_logger.stop()
        self.logger.info("Shutting down")
        self.win.close()
        if self.device_manager is not None:
            self.device_manager.close_streams()

    def as_dict(self):

        dictionary = {"win": self.win,
                      "path": self.path,
                      "subj_id": self.session_name,
                      "eye_tracker": self.eye_tracker,
                      "marker_outlet": None,
                      "mbients": None
                      }

        if self.device_manager is not None:
            dictionary["marker_outlet"] = self.device_manager.streams["marker"]
            dictionary["mbients"] = self.device_manager.get_mbient_streams()

        return dictionary
