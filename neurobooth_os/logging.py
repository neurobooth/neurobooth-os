import os
import logging
from datetime import datetime


def make_session_logger(session_folder: str, machine_name: str, log_level=logging.DEBUG) -> logging.Logger:
    formatter = logging.Formatter('|%(levelname)s| [%(asctime)s] %(filename)s, %(funcName)s, L%(lineno)d> %(message)s')

    logger = logging.getLogger('session')
    time_str = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    file_handler = logging.FileHandler(os.path.join(session_folder, f'{machine_name}_session_{time_str}.log'))
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.setLevel(log_level)

    return logger
