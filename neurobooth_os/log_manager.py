import os
import logging
import sys
from datetime import datetime
from typing import Optional

from neurobooth_os.config import neurobooth_config

LOG_FORMAT = logging.Formatter('|%(levelname)s| [%(asctime)s] %(filename)s, %(funcName)s, L%(lineno)d> %(message)s')

DEFAULT_LOG_PATH = neurobooth_config["default_log_path"]


def make_session_logger(session_folder: str, machine_name: str, log_level=logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger('session')
    time_str = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")
    file_handler = logging.FileHandler(os.path.join(session_folder, f'{machine_name}_session_{time_str}.log'))
    file_handler.setLevel(log_level)
    file_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(file_handler)
    logger.setLevel(log_level)
    return logger


def make_session_logger_debug(
        file: Optional[str] = None,
        console: bool = False,
        log_level=logging.DEBUG
) -> logging.Logger:
    logger = logging.getLogger('session')

    if file is not None:
        file_handler = logging.FileHandler(file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(LOG_FORMAT)
        logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(LOG_FORMAT)
        logger.addHandler(console_handler)

    logger.setLevel(log_level)
    return logger


def make_default_logger(
        log_path=DEFAULT_LOG_PATH,
        log_level=logging.DEBUG,
) -> logging.Logger:
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    logger = logging.getLogger('default')
    time_str = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")
    file = os.path.join(log_path, f'default_{time_str}.log')

    file_handler = logging.FileHandler(file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(console_handler)

    make_session_logger_debug(file=file)

    logger.setLevel(log_level)
    return logger
