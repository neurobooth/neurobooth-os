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

SESSION_ID: str = ""
SUBJECT_ID: str = ""

DB_LOGGER: Optional[logging.Logger] = None


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
                   fallback_log_path: str = None) -> logging.Logger:
    """Returns a logger that logs to the database and sets the subject id and session to be used for subsequent
    logging calls.

    If the subject or session should be cleared, the argument should be an empty string. Passing None, will NOT reset
    """
    import neurobooth_os.iout.metadator

    global SUBJECT_ID, SESSION_ID, DB_LOGGER

    if subject is not None:
        SUBJECT_ID = subject
    if session is not None:
        SESSION_ID = session

    # Don't reinitialize the logger
    if DB_LOGGER is None:
        logger = logging.getLogger('db')
        logger.addHandler(get_db_log_handler(fallback_log_path))
        extra = {"device": ""}
        logging.LoggerAdapter(logger, extra)
        DB_LOGGER = logger
    return DB_LOGGER


def get_default_log_handler(
        log_path=DEFAULT_LOG_PATH,
        log_level=logging.DEBUG,
):
    """Returns a log handler suitable for default logging
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
    A :class:`logging.Handler` that logs to the `log` PostgreSQL table
    Does not use :class:`PostgreSQL`, keeping its own connection, in autocommit
    mode.
    .. DANGER:
        Beware explicit or automatic locks taken out in the main requests'
        transaction could deadlock with this INSERT!
        In general, avoid touching the log table entirely. SELECT queries
        do not appear to block with INSERTs. If possible, touch the log table
        in autocommit mode only.
    `db_settings` is passed to :meth:`psycopg2.connect` as kwargs
    (``connect(**db_settings)``).
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
        try:
            self._get_logger_connection()
        except Exception as Argument:
            msg = "Unable to connect to database for logging. Falling back to default file logging."
            self.handle_logging_exception()
            logging.getLogger("db").exception(msg)

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
        except Exception as Argument:
            msg = "An exception occurred attempting to log to DB. Falling back to file-system log."
            self.handle_logging_exception()
            self.handleError(record)
            logging.getLogger("db").exception(msg)

    def _get_logger_connection(self):
        self.connection = metadator.get_conn(neurobooth_config["database"]["dbname"])
        self.connection.autocommit = True
        self.cursor = self.connection.cursor()

    def handle_logging_exception(self):
        logger = logging.getLogger("db")
        if self in logger.handlers:
            logger.removeHandler(self)
        default_handler = get_default_log_handler(self.fallback_log_path)
        if default_handler not in logger.handlers:
            logger.addHandler(default_handler)

def get_db_log_handler(
        fallback_log_path: str = DEFAULT_LOG_PATH,
        log_level=logging.DEBUG,):
    return PostgreSQLHandler(fallback_log_path, log_level)
