"""Liveness and crash reporting for the Neurobooth services (CTR, STM, ACQ_n).

Two things the database log cannot do on its own:

- **Heartbeat.** A hard crash (access violation, SIGABRT) kills the process before it can
  write a ``log_application`` row, so from the database a dead service looks the same as an
  idle one. ``ServiceHeartbeat`` keeps one ``service_heartbeat`` row per process launch
  current. A row whose ``last_beat`` is stale and whose ``stopped_at`` is NULL is a process
  that died without shutting down.
- **Backfill.** On startup, crash traces from ``neurobooth_crash_<service>.log`` and records
  that fell back to ``neurobooth_db_log_fallback_<service>.log`` while the database was
  unreachable are logged to the ``app`` logger, so they reach ``log_application``.

Call ``start_service_monitor()`` once the database logger exists and ``stop()`` the returned
heartbeat on shutdown.
"""

import logging
import os
import platform
from datetime import datetime
from pathlib import Path
from threading import Event, Thread

import neurobooth_os.current_release as release
import neurobooth_os.log_manager as log_manager
from neurobooth_os.iout import metadator

HEARTBEAT_INTERVAL_SEC = 30.0

# Bounds the startup backfill so a long database outage can't bury the log in replayed rows.
MAX_RECOVERED_RECORDS = 200

_FALLBACK_LEVELS = {
    b"DEBUG": logging.DEBUG,
    b"INFO": logging.INFO,
    b"WARNING": logging.WARNING,
    b"ERROR": logging.ERROR,
    b"CRITICAL": logging.CRITICAL,
}


class ServiceHeartbeat(Thread):
    """Daemon thread that upserts this process's ``service_heartbeat`` row on an interval.

    Each beat is an idempotent upsert keyed on (server_id, pid, process_start), so the row
    recovers on its own after a database outage. Failures are logged once per outage rather
    than on every beat.
    """

    _upsert_query = (
        "INSERT INTO service_heartbeat "
        "(service_id, server_id, pid, process_start, last_beat, session_id, release_version) "
        "VALUES (%(service_id)s, %(server_id)s, %(pid)s, %(process_start)s, now(), "
        "%(session_id)s, %(release_version)s) "
        "ON CONFLICT (server_id, pid, process_start) "
        "DO UPDATE SET last_beat = now(), session_id = EXCLUDED.session_id"
    )
    _stop_query = (
        "UPDATE service_heartbeat SET last_beat = now(), stopped_at = now(), "
        "exit_code = %(exit_code)s "
        "WHERE server_id = %(server_id)s AND pid = %(pid)s AND process_start = %(process_start)s"
    )

    def __init__(self, service_id: str, interval_sec: float = HEARTBEAT_INTERVAL_SEC):
        """Create the heartbeat thread; call ``start()`` to begin beating.

        Args:
            service_id: The service this process runs, e.g. ``"ACQ_0"``.
            interval_sec: Seconds between beats.
        """
        super().__init__(name=f"ServiceHeartbeat-{service_id}", daemon=True)
        self.service_id = service_id
        self.interval_sec = interval_sec
        self.server_id = platform.uname().node
        self.pid = os.getpid()
        self.process_start = datetime.now().astimezone()
        self._stop_event = Event()
        self._connection = None
        self._failing = False
        self._logger = logging.getLogger(log_manager.APP_LOG_NAME)

    def run(self) -> None:
        self._beat()
        while not self._stop_event.wait(self.interval_sec):
            self._beat()

    def stop(self, exit_code: int) -> None:
        """Stop beating and mark the row as cleanly stopped with the process's exit code.

        Args:
            exit_code: The code the process is about to exit with.
        """
        self._stop_event.set()
        self.join(timeout=self.interval_sec)
        if self.is_alive():
            # The thread still holds the connection; using it from here is not safe.
            self._logger.warning("Heartbeat thread did not stop; the stop time was not recorded.")
            return
        self._execute(self._stop_query, {**self._key(), "exit_code": exit_code})
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _beat(self) -> None:
        self._execute(
            self._upsert_query,
            {
                **self._key(),
                "service_id": self.service_id,
                "session_id": log_manager.SESSION_ID or None,
                "release_version": release.version,
            },
        )

    def _key(self) -> dict:
        return {"server_id": self.server_id, "pid": self.pid, "process_start": self.process_start}

    def _execute(self, query: str, args: dict) -> None:
        try:
            if self._connection is None:
                self._connection = metadator.get_database_connection(connect_timeout=3)
                self._connection.autocommit = True
            with self._connection.cursor() as cursor:
                cursor.execute(query, args)
        except Exception:
            if not self._failing:
                self._logger.warning("Service heartbeat write failed; retrying each beat.", exc_info=True)
            self._failing = True
            if self._connection is not None:
                self._connection.close()  # ManagedConnection.close() never raises
                self._connection = None
            return
        if self._failing:
            self._logger.info("Service heartbeat writes recovered.")
        self._failing = False


def start_service_monitor(service_id: str, logger: logging.Logger) -> ServiceHeartbeat:
    """Backfill this service's local crash and fallback logs, then start its heartbeat.

    A backfill failure is logged and does not stop the service from starting.

    Args:
        service_id: The service this process runs, e.g. ``"ACQ_0"``.
        logger: The database-backed ``app`` logger.

    Returns:
        The running heartbeat; call ``stop(exit_code)`` on it during shutdown.
    """
    try:
        backfill_crash_log(log_manager.crash_log_path(service_id), logger)
    except Exception:
        logger.exception("Crash-log backfill failed for %s.", service_id)
    try:
        backfill_db_fallback_log(log_manager.db_fallback_log_path(service_id), logger)
    except Exception:
        logger.exception("DB-fallback-log backfill failed for %s.", service_id)

    heartbeat = ServiceHeartbeat(service_id)
    heartbeat.start()
    return heartbeat


def backfill_crash_log(log_path: Path, logger: logging.Logger) -> int:
    """Log every crash trace written to ``log_path`` since the last backfill.

    The file is split into blocks at the headers ``enable_crash_handler`` writes. A block with
    anything after its header is a faulthandler trace from an earlier launch. The current
    process's own block is never read, and the next backfill starts at its header, so a trace
    this process writes later is picked up by the next launch.

    Args:
        log_path: The service's crash log.
        logger: Logger to report each trace to, at ERROR.

    Returns:
        The number of traces logged.
    """
    if not log_path.exists():
        return 0
    data = log_path.read_bytes()
    start = _read_offset(log_path, len(data))

    headers = list(log_manager.CRASH_LOG_HEADER_PATTERN.finditer(data))
    end = len(data)
    for header in reversed(headers):
        if int(header.group("pid")) == os.getpid():
            end = header.start()
            break

    traces_logged = 0
    for index, header in enumerate(headers):
        if header.start() < start or header.start() >= end:
            continue
        block_end = headers[index + 1].start() if index + 1 < len(headers) else len(data)
        trace = data[header.end():min(block_end, end)].decode("utf-8", errors="replace").strip()
        if not trace:
            continue
        logger.error(
            "Crash trace recovered from %s (%s launched %s, PID %s):\n%s",
            log_path.name,
            header.group("service_id").decode(),
            header.group("started").decode(),
            header.group("pid").decode(),
            trace,
            extra={"device": "crash_log"},
        )
        traces_logged += 1

    _write_offset(log_path, end)
    return traces_logged


def backfill_db_fallback_log(log_path: Path, logger: logging.Logger) -> int:
    """Re-log records that ``PostgreSQLHandler`` wrote to ``log_path`` while the DB was down.

    WARNING and above are re-logged individually at their original level, up to
    ``MAX_RECOVERED_RECORDS``; everything else is reported as a count. Each record's text,
    including its original timestamp and source line, becomes the message. If the database
    drops during the backfill, the re-logged records land past the saved offset and are
    picked up by the next launch.

    Args:
        log_path: The service's DB-fallback log.
        logger: Logger to re-log the records to.

    Returns:
        The number of records re-logged individually.
    """
    if not log_path.exists():
        return 0
    data = log_path.read_bytes()
    start = _read_offset(log_path, len(data))

    records_logged = 0
    records_summarized = 0
    for record in _split_fallback_records(data[start:]):
        level_name = record.split(b"] ", 1)[1].split(b" ", 1)[0] if b"] " in record else b""
        level = _FALLBACK_LEVELS.get(level_name, logging.INFO)
        if level >= logging.WARNING and records_logged < MAX_RECOVERED_RECORDS:
            logger.log(
                level,
                "Recovered from %s: %s",
                log_path.name,
                record.decode("utf-8", errors="replace").rstrip(),
                extra={"device": "db_fallback_log"},
            )
            records_logged += 1
        else:
            records_summarized += 1

    if records_summarized:
        logger.warning(
            "%d further records in %s were not re-logged individually (below WARNING, or past "
            "the limit of %d); read the file for them.",
            records_summarized,
            log_path.name,
            MAX_RECOVERED_RECORDS,
        )

    _write_offset(log_path, len(data))
    return records_logged


def _split_fallback_records(data: bytes) -> list:
    """Split fallback-log bytes into records: a ``[timestamp] LEVEL`` line plus any traceback lines."""
    records = []
    for line in data.splitlines(keepends=True):
        if line.startswith(b"[") or not records:
            records.append(line)
        else:
            records[-1] += line
    return [record for record in records if record.strip()]


def _offset_path(log_path: Path) -> Path:
    return log_path.with_name(f"{log_path.name}.offset")


def _read_offset(log_path: Path, file_size: int) -> int:
    """Return the byte offset the last backfill reached, or 0 if none, or if the log shrank."""
    offset_path = _offset_path(log_path)
    if not offset_path.exists():
        return 0
    offset = int(offset_path.read_text().strip() or 0)
    return offset if offset <= file_size else 0


def _write_offset(log_path: Path, offset: int) -> None:
    offset_path = _offset_path(log_path)
    temporary_path = offset_path.with_name(f"{offset_path.name}.tmp")
    temporary_path.write_text(str(offset))
    os.replace(temporary_path, offset_path)
