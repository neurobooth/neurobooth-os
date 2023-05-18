import os
import logging


def make_session_logger(session_folder: str, machine_name: str, log_level=logging.DEBUG) -> logging.Logger:
    formatter = logging.Formatter('|%(levelname)s| [%(asctime)s] %(filename)s, %(funcName)s, L%(lineno)d> %(message)s')

    logger = logging.getLogger('session')
    file_handler = logging.FileHandler(os.path.join(session_folder, f'{machine_name}_session.log'))
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
