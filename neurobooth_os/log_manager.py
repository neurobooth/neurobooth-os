import json
import os
import logging
import sys
from datetime import datetime
from typing import Optional, List, Dict, Any
import psutil
from threading import Thread, Event
import platform
import traceback

from neurobooth_terra import Table
from pydantic import BaseModel

import neurobooth_os.config as config
from neurobooth_os.iout import metadator
from neurobooth_os.msg.messages import Message

LOG_FORMAT = logging.Formatter('|%(levelname)s| [%(asctime)s] %(filename)s, %(funcName)s, L%(lineno)d> %(message)s')

# Globals: Set using make_db_logger(). Must be set to log session and subject data
SESSION_ID: str = ""
SUBJECT_ID: str = ""

# Create APP_LOGGER as a singleton. Otherwise, multiple calls to make_db_logger will add redundant handlers
APP_LOGGER: Optional[logging.Logger] = None

# Name of the Application Logger, for use in retrieving the appropriate logger from the logging module
APP_LOG_NAME = "app"
# Name of the System Resource Logger
SYS_RES_LOG_NAME = "sys_resource"


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
                   fallback_log_path: str = None,
                   log_level: int = logging.DEBUG) -> logging.Logger:
    """Returns a logger that logs to the database and sets the subject id and session to be used for subsequent
    logging calls.

    NOTE: If the subject or session should be cleared, the argument should be an empty string.
    Passing None will NOT reset those values
    """

    if fallback_log_path is None:
        fallback_log_path = config.neurobooth_config.default_log_path

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
        logger.setLevel(log_level)
        extra = {"device": ""}
        logging.LoggerAdapter(logger, extra)
        APP_LOGGER = logger
    return APP_LOGGER


def get_default_log_handler(
        log_path: Optional[str] = None,
        log_level=logging.DEBUG,
):
    """Returns a log handler suitable for logging when the DB isn't available
    """
    if log_path is None:
        log_path = config.neurobooth_config.default_log_path

    if not os.path.exists(log_path):
        os.makedirs(log_path)
    time_str = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")
    file = os.path.join(log_path, f'default_{time_str}.log')

    file_handler = logging.FileHandler(file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(LOG_FORMAT)
    return file_handler


def make_default_logger(
        log_path: Optional[str] = None,
        log_level=logging.DEBUG,
        validate_paths: bool = True
) -> logging.Logger:
    if config.neurobooth_config is None:
        config.load_config(None, validate_paths)
    if log_path is None:
        log_path = config.neurobooth_config.default_log_path

    logger = logging.getLogger('default')
    logger.addHandler(get_default_log_handler(log_path, log_level))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(LOG_FORMAT)
    logger.addHandler(console_handler)

    # make_session_logger_debug(file=file)

    logger.setLevel(log_level)
    return logger


def log_message_received(message: Message, logger) -> None:
    message_dict = dict(message)
    message_dict['body'] = message.body.model_dump_json()
    logger.info(f'MESSAGE RECEIVED: {message_dict}')


class CpuUsage(BaseModel):
    name: str
    pct: float


class DiskUsage(BaseModel):
    name: str
    bytes_read: int
    bytes_written: int


class SysResourceRecord(BaseModel):
    """
    System Resource Log record
    """
    machine_name: str  # name of machine being logged, e.g. 'ACQ'
    session_start: datetime  # timestamp when logging starts
    created_at: Optional[datetime] = None  # Database server-time of record insertion
    ram_used: int  #
    ram_total: int  #
    swap_used: int  #
    swap_total: int  #
    net_recd: int  #
    net_sent: int  #
    cpu_usage: List[CpuUsage]  # list of CPU utilization records
    disk_usage: List[DiskUsage]  # list of disk utilization records


class SystemResourceLogger(Thread):
    """
    A "logger" that isn't really part of the typical python logging family, which seemed to add too much complexity for
    something so simple.

    Logs system resources, mostly provided by psutil, into the table log_system_resource
    Scalar values are logged as standard columns, but resources that are likely to change
    (e.g. the number of disks or CPUs in a system) are written as JSON (jsonb) columns in Postgres
    """

    def __init__(self, machine_name: str, log_interval_sec: float = 10):
        """
        Create a new system resource logging thread.
        :param machine_name: The name of the machine the thread is running on.
        :param log_interval_sec: How often to log resource usage (in seconds).
        """
        super().__init__()
        self.machine_name = machine_name
        self.session_start = datetime.now()
        self.connection = metadator.get_database_connection()
        self.connection.autocommit = True
        self.log_interval_sec = log_interval_sec
        self.sleep_event = Event()
        self.table = Table("log_system_resource", conn=self.connection)

    def run(self) -> None:
        # Perform initial calls that return meaningless data
        psutil.cpu_percent(percpu=True)

        # Main logging loop
        while not self.sleep_event.wait(self.log_interval_sec):  # Will return True if event set by stop()
            cpu: List[CpuUsage] = self.log_cpu()
            ram: Dict[str, int] = self.log_memory()
            disk: List[DiskUsage] = self.log_disk_io()
            net: Dict[str, int] = self.log_network_io()

            record: SysResourceRecord = SysResourceRecord(
                machine_name=self.machine_name,
                session_start=self.session_start,
                ram_used=ram['RAM_used'],
                ram_total=ram['RAM_total'],
                swap_used=ram['SWAP_used'],
                swap_total=ram['SWAP_total'],
                net_recd=net['Network_bytes_received'],
                net_sent=net['Network_bytes_sent'],
                disk_usage=disk,
                cpu_usage=cpu,
            )
            self.emit(record)

    @staticmethod
    def log_cpu() -> List[CpuUsage]:
        cpu_pct: List[float] = psutil.cpu_percent(percpu=True)
        return [CpuUsage(name=f'CPU_{i}', pct=pct) for i, pct in enumerate(cpu_pct)]

    @staticmethod
    def log_memory() -> Dict[str, Any]:
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return {
            'RAM_used': ram.total - ram.available,
            'RAM_total': ram.total,
            'SWAP_used': swap.used,
            'SWAP_total': swap.total,
        }

    @staticmethod
    def log_disk_io() -> List[DiskUsage]:
        disk_io: Dict[str, Any] = psutil.disk_io_counters(perdisk=True)

        results = []
        for i, (name, io) in enumerate(disk_io.items()):
            results.append(
                DiskUsage(
                    name=name,
                    bytes_read=io.read_bytes,
                    bytes_written=io.write_bytes)
            )
        return results

    @staticmethod
    def log_network_io() -> Dict[str, Any]:
        net_io = psutil.net_io_counters()
        return {
            'Network_bytes_received': net_io.bytes_recv,
            'Network_bytes_sent': net_io.bytes_sent,
        }

    def emit(self, record: SysResourceRecord):

        disks = json.dumps([item.model_dump() for item in record.disk_usage])
        cpus = json.dumps([item.model_dump() for item in record.cpu_usage])
        return self.table.insert_rows([(str(
            record.machine_name),
                                   record.session_start,
                                   record.ram_used,
                                   record.ram_total,
                                   record.swap_used,
                                   record.swap_total,
                                   record.net_recd,
                                   record.net_sent,
                                   disks,
                                   cpus)],
            cols=["machine_name", "session_start", "ram_used", "ram_total", "swap_used",
                  'swap_total', "net_recd", "net_sent", "disk_usage", "cpu_usage"
                  ])

    def stop(self) -> None:
        """Stop logging and wait for the thread to complete."""
        self.sleep_event.set()
        self.connection.close()
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

    def __init__(self, fallback_log_path: str = None, log_level=logging.DEBUG):
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
                "server_type": config.get_server_name_from_env(),
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
        self.connection = metadator.get_database_connection()
        self.connection.autocommit = True
        self.cursor = self.connection.cursor()

    def fallback_to_local_handler(self):
        logger = logging.getLogger(APP_LOG_NAME)
        if self in logger.handlers:
            logger.removeHandler(self)
        default_handler = get_default_log_handler(self.fallback_log_path, logging.DEBUG)
        if default_handler not in logger.handlers:
            logger.addHandler(default_handler)


def _test_log_handler_fallback():
    """FOR TESTING PURPOSES ONLY
    Causes logger to fall back to filesystem logging without an actual failure occurring"""
    logger = logging.getLogger(APP_LOG_NAME)
    for handler in logger.handlers:
        if handler.name == "db_handler":
            handler.fallback_to_local_handler()
