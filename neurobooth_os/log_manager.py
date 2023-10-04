import os
import logging
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
import psutil
from threading import Thread, Event
import json
import platform
import traceback

from neurobooth_os.config import neurobooth_config
from neurobooth_os.iout import metadator

LOG_FORMAT = logging.Formatter('|%(levelname)s| [%(asctime)s] %(filename)s, %(funcName)s, L%(lineno)d> %(message)s')

DEFAULT_LOG_PATH = neurobooth_config["default_log_path"]

# Globals: Set using make_db_logger(). Must be set to log session and subject data
SESSION_ID: str = ""
SUBJECT_ID: str = ""

# Create APP_LOGGER as a singleton. Otherwise, multiple calls to make_db_logger will add redundant handlers
APP_LOGGER: Optional[logging.Logger] = None
TASK_PARAM_LOGGER: Optional[logging.Logger] = None

# Name of the Application Logger, for use in retrieving the appropriate logger from the logging module
APP_LOG_NAME = "app"
TASK_PARAM_LOG_NAME = "task-param"



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


def make_db_logger(subject: str = None,
                   session: str = None,
                   fallback_log_path: str = DEFAULT_LOG_PATH,
                   log_level: int = logging.DEBUG) -> logging.Logger:
    """Returns a logger that logs to the database and sets the subject id and session to be used for subsequent
    logging calls.

    NOTE: If the subject or session should be cleared, the argument should be an empty string.
    Passing None will NOT reset those values
    """

    global SUBJECT_ID, SESSION_ID, APP_LOGGER

    if subject is not None:
        SUBJECT_ID = subject
    if session is not None:
        SESSION_ID = session

    # Don't reinitialize the logger if one exists
    if APP_LOGGER is None:
        logger = logging.getLogger(APP_LOG_NAME)
        handler = PostgreSQLHandler(fallback_log_path, log_level)
        logger.addHandler(handler)
        extra = {"device": ""}
        logging.LoggerAdapter(logger, extra)
        APP_LOGGER = logger
    return APP_LOGGER


def get_default_log_handler(
        log_path=DEFAULT_LOG_PATH,
        log_level=logging.DEBUG,
):
    """Returns a log handler suitable for logging when the DB isn't available
    """

    if not os.path.exists(log_path):
        os.makedirs(log_path)
    time_str = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")
    file = os.path.join(log_path, f'default_{time_str}.log')

    file_handler = logging.FileHandler(file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(LOG_FORMAT)
    return file_handler


def make_default_logger(
        log_path=DEFAULT_LOG_PATH,
        log_level=logging.DEBUG,
) -> logging.Logger:
    logger = logging.getLogger('default')
    logger.addHandler(get_default_log_handler(log_path, log_level))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(console_handler)

    # make_session_logger_debug(file=file)

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


class PostgreSQLHandler(logging.Handler):
    """
    A :class:`logging.Handler` that logs to the `log_application` PostgreSQL table

    This handler has its own connection in autocommit mode.
    .. DANGER:
        SELECT queries do not appear to block with INSERTs. Touch the log table in autocommit mode only.
    """

    _query = "INSERT INTO log_application " \
             "(session_id, subject_id, server_type, server_id, server_time, log_level, device, " \
             "filename, function, line_no, message, traceback)" \
             " VALUES " \
             " (%(session_id)s, %(subject_id)s, %(server_type)s, %(server_id)s, %(server_time)s, %(log_level)s, " \
             " %(device)s, %(filename)s, %(function)s, %(line_no)s, %(message)s, %(traceback)s)"

    # see TYPE log_level
    _levels = ('debug', 'info', 'warning', 'error', 'critical')

    def __init__(self, fallback_log_path:str = None, log_level=logging.DEBUG):
        super(PostgreSQLHandler, self).__init__()
        self.fallback_log_path = fallback_log_path
        self.setLevel(log_level)
        self.name = "db_handler"
        try:
            self._get_logger_connection()
        except Exception:
            msg = "Unable to connect to database for logging. Falling back to default file logging."
            self.fallback_to_local_handler()
            logging.getLogger(APP_LOG_NAME).exception(msg)

    def close(self):
        """Close this log handler and its DB connection """
        logging.getLogger(APP_LOG_NAME).debug("Closing app log db connection")
        logging.getLogger(APP_LOG_NAME).removeHandler(self)
        if self.connection is not None:
            self.connection.close()
        global APP_LOGGER
        APP_LOGGER = None

    def emit(self, record):
        try:
            level = record.levelname.lower()
            if level not in self._levels:
                level = "debug"

            if record.exc_info:
                lines = traceback.format_exception(*record.exc_info)
                traceback_text = ''.join(lines)
            else:
                traceback_text = None

            args = {
                "log_level": level,
                "message": record.getMessage(),
                "function": record.funcName,
                "filename": record.filename,
                "line_no": record.lineno,
                "traceback": traceback_text,
                "server_type": neurobooth_config["server_name"],
                "server_id": platform.uname().node,
                "subject_id": SUBJECT_ID,
                "session_id": SESSION_ID,
                "server_time": datetime.fromtimestamp(record.created),
                "device": getattr(record, "device", None),
            }

            self.cursor.execute(self._query, args)

        except Exception:
            msg = "An exception occurred attempting to log to DB. Falling back to file-system log."
            self.fallback_to_local_handler()
            self.handleError(record)
            logging.getLogger(APP_LOG_NAME).exception(msg)

    def _get_logger_connection(self):
        self.connection = metadator.get_conn(neurobooth_config["database"]["dbname"])
        self.connection.autocommit = True
        self.cursor = self.connection.cursor()

    def fallback_to_local_handler(self):
        logger = logging.getLogger(APP_LOG_NAME)
        if self in logger.handlers:
            logger.removeHandler(self)
        default_handler = get_default_log_handler(self.fallback_log_path)
        if default_handler not in logger.handlers:
            logger.addHandler(default_handler)


def _test_log_handler_fallback():
    """FOR TESTING PURPOSES ONLY
    Causes logger to fall back to filesystem logging without an actual failure occurring"""
    logger = logging.getLogger(APP_LOG_NAME)
    for handler in logger.handlers:
        if handler.name == "db_handler":
            handler.fallback_to_local_handler()


class TaskParamLogHandler(logging.Handler):
    """
    A :class:`logging.Handler` that logs to the `log_task_params` PostgreSQL table

    This handler has its own connection in autocommit mode.
    .. DANGER:
        SELECT queries do not appear to block with INSERTs. Touch the log table in autocommit mode only.
    """

    _query = "INSERT INTO log_task_params " \
             "(session_id, subject_id, name, value) " \
             " VALUES " \
             " (%(session_id)s, %(subject_id)s, %(name)s, %(value)s)"

    def __init__(self):
        super(TaskParamLogHandler, self).__init__()
        self.setLevel("info")
        self.name = "task_param_log_handler"
        try:
            self._get_logger_connection()
        except Exception:
            msg = "Unable to connect to database for task parameter logging."
            logging.getLogger(APP_LOG_NAME).exception(msg)

    def close(self):
        """Close this log handler and its DB connection """
        # TODO(larry): Should we try to get the loggers from their respective globals?
        app_logger = logging.getLogger(APP_LOG_NAME)
        app_logger.debug("Closing task param log db connection")
        task_logger = logging.getLogger(TASK_PARAM_LOG_NAME)
        task_logger.removeHandler(self)
        if self.connection is not None:
            self.connection.close()
        global DB_LOGGER
        DB_LOGGER = None

    def emit(self, record):
        try:
            args = {
                "value": getattr(record, "value", None),
                "name": getattr(record, "name", None),
                "subject_id": SUBJECT_ID,
                "session_id": SESSION_ID,
            }

            self.cursor.execute(self._query, args)

        except Exception:
            msg = "An exception occurred attempting to log to DB. Falling back to file-system log."
            # TODO(larry): ensure that log exists before logging
            logging.getLogger(APP_LOG_NAME).exception(msg)

    def _get_logger_connection(self):
        self.connection = metadator.get_conn(neurobooth_config["database"]["dbname"])
        self.connection.autocommit = False  # Log all params in a single transaction
        self.cursor = self.connection.cursor()
