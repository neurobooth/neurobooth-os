import os
import logging
import sys
from datetime import datetime


LOG_FORMAT = logging.Formatter('|%(levelname)s| [%(asctime)s] %(filename)s, %(funcName)s, L%(lineno)d> %(message)s')


def make_session_logger(session_folder: str, machine_name: str, log_level=logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger('session')
    time_str = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")
    file_handler = logging.FileHandler(os.path.join(session_folder, f'{machine_name}_session_{time_str}.log'))
    file_handler.setLevel(log_level)
    file_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(file_handler)
    logger.setLevel(log_level)
    return logger


def make_iphone_dump_logger(log_level=logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger('iphone_dump')
    time_str = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")

    file_handler = logging.FileHandler(f'D:/neurobooth_logs/iphone_dump_{time_str}.log')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(console_handler)

    logger.setLevel(log_level)
    return logger
