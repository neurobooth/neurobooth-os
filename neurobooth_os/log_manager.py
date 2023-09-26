import os
import logging
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
import psutil
from threading import Thread, Event
import json

from neurobooth_os.config import neurobooth_config

LOG_FORMAT = logging.Formatter('|%(levelname)s| [%(asctime)s] %(filename)s, %(funcName)s, L%(lineno)d> %(message)s')

DEFAULT_LOG_PATH = neurobooth_config["default_log_path"]

SESSION_ID: str = ""

SUBJECT_ID: str = ""


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


def make_db_logger(subject: str, session: str, device: str = None) -> logging.Logger:
    """Returns a logger that logs to the database and sets the subject id and session to be used for subsequent
    logging calls.

    If the subject or session should be cleared, the argument should be an empty string. Passing None, will not reset
    to allow this logger to be used when the function that is logging does not itself have access to the session/subject,
    but it remains valid none-the-less
    """
    import neurobooth_os.iout.metadator

    global SUBJECT_ID, SESSION_ID
    if subject is not None:
        SUBJECT_ID = subject
    if session is not None:
        SESSION_ID = session

    logger = logging.getLogger('db')
    logger.addHandler(neurobooth_os.iout.metadator.get_db_log_handler())
    extra = {
        "session": SESSION_ID,
        "subject": SUBJECT_ID,
        "device": device
    }
    logging.LoggerAdapter(logger, extra)
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


class SystemResourceLogger(Thread):
    """Logs CPU, network, and disk usage at regular intervals."""
    LOG_FORMAT = logging.Formatter('[%(asctime)s] %(message)s')

    def __init__(self, session_folder: str, machine_name: str, log_interval_sec: float = 10):
        """
        Create a new system resource logging thread.
        :param session_folder: The folder to save the log to.
        :param machine_name: The name of the machine the thread is running on.
        :param log_interval_sec: How often to log resource usage (in seconds).
        """
        super().__init__()
        self.logger = SystemResourceLogger.__create_log(session_folder, machine_name)
        self.log_interval_sec = log_interval_sec
        self.sleep_event = Event()

    @staticmethod
    def __create_log(session_folder: str, machine_name: str) -> logging.Logger:
        logger = logging.getLogger('resource_log')
        time_str = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")
        file_handler = logging.FileHandler(
            os.path.join(session_folder, f'{machine_name}_system_resource_{time_str}.log')
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(SystemResourceLogger.LOG_FORMAT)
        logger.addHandler(file_handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def run(self) -> None:
        # Perform initial calls that return meaningless data
        psutil.cpu_percent(percpu=True)

        # Main logging loop
        while not self.sleep_event.wait(self.log_interval_sec):  # Will return True if event set by stop()
            results = {}
            results.update(self.log_cpu())
            results.update(self.log_memory())
            results.update(self.log_disk_io())
            results.update(self.log_network_io())
            self.logger.info(f'JSON> {json.dumps(results)}')

    def log_cpu(self) -> Dict[str, Any]:
        cpu_pct: List[float] = psutil.cpu_percent(percpu=True)

        cpu_pct_str = ', '.join([f'{i}: {pct:.1f}%' for i, pct in enumerate(cpu_pct)])
        self.logger.info(f'CPU> {cpu_pct_str}')

        return {f'CPU_{i}_pct': pct for i, pct in enumerate(cpu_pct)}

    def log_memory(self) -> Dict[str, Any]:
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()

        self.logger.info(f'RAM> {ram.total - ram.available} / {ram.total} ({ram.percent:.1f}%)')
        self.logger.info(f'SWAP> {swap.used} / {swap.total} ({swap.percent:.1f}%)')

        return {
            'RAM_used': ram.total - ram.available,
            'RAM_total': ram.total,
            'SWAP_used': swap.used,
            'SWAP_total': swap.total,
        }

    def log_disk_io(self) -> Dict[str, Any]:
        disk_io: Dict[str, Any] = psutil.disk_io_counters(perdisk=True)

        results = {}
        for i, (name, io) in enumerate(disk_io.items()):
            self.logger.info(f'DISK {i}> ({name}) {io.read_bytes} bytes read, {io.write_bytes} bytes written')
            results.update({
                f'Disk_{i}_name': name,
                f'Disk_{i}_bytes_read': io.read_bytes,
                f'Disk_{i}_bytes_written': io.write_bytes,
            })

        return results

    def log_network_io(self) -> Dict[str, Any]:
        net_io = psutil.net_io_counters()

        self.logger.info(f'NET> {net_io.bytes_recv} bytes received, {net_io.bytes_sent} bytes sent')

        return {
            'Network_bytes_received': net_io.bytes_recv,
            'Network_bytes_sent': net_io.bytes_sent,
        }

    def stop(self) -> None:
        """Stop logging and wait for the thread to complete."""
        self.sleep_event.set()
        self.join(timeout=self.log_interval_sec + 1)
