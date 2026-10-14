"""Tests for crash/error capture that the database log can't do on its own.

Covers the exception hooks and per-service crash log in ``log_manager``, and the
heartbeat and startup backfill in ``service_monitor``. Regression coverage for
failures that left no ``log_application`` row: a device thread dying with its
traceback printed only to the hidden console, and hard crashes whose
faulthandler trace sat in a local file nobody read.
"""
from __future__ import annotations

import logging
import sys
import threading
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

import neurobooth_os.log_manager as lm
import neurobooth_os.service_monitor as sm


# --- Exception hooks ---------------------------------------------------------


@contextmanager
def installed_hooks(monkeypatch):
    """Install the hooks over recording stand-ins for the previous hooks.

    Used inside the test body, not as a fixture: pytest replaces
    ``threading.excepthook`` with its own for the duration of each test call,
    and restores it afterwards, so hooks installed during fixture setup would
    never see a thread exception.
    """
    with monkeypatch.context() as patch:
        previous = MagicMock(name="previous_excepthook")
        previous_thread = MagicMock(name="previous_thread_excepthook")
        patch.setattr(sys, "excepthook", previous)
        patch.setattr(threading, "excepthook", previous_thread)
        patch.setattr(lm, "_exception_hooks_installed", False)
        lm.install_exception_hooks()
        yield previous, previous_thread


def _critical_records(caplog):
    return [r for r in caplog.records if r.name == lm.APP_LOG_NAME and r.levelno == logging.CRITICAL]


def test_thread_exception_is_logged_with_traceback(monkeypatch, caplog):
    def die():
        raise RuntimeError("camera thread died")

    with installed_hooks(monkeypatch) as (_, previous_thread):
        worker = threading.Thread(target=die, name="FLIR-save")
        worker.start()
        worker.join()

    [record] = _critical_records(caplog)
    assert "FLIR-save" in record.getMessage()
    assert record.exc_info[1].args == ("camera thread died",)
    previous_thread.assert_called_once()  # console output unchanged


def test_thread_system_exit_is_not_logged(monkeypatch, caplog):
    with installed_hooks(monkeypatch):
        worker = threading.Thread(target=sys.exit)
        worker.start()
        worker.join()

    assert _critical_records(caplog) == []


def test_main_thread_exception_is_logged_and_chained(monkeypatch, caplog):
    try:
        raise ValueError("escaped main")
    except ValueError:
        exc_info = sys.exc_info()

    with installed_hooks(monkeypatch) as (previous, _):
        sys.excepthook(*exc_info)

    [record] = _critical_records(caplog)
    assert record.exc_info[1] is exc_info[1]
    previous.assert_called_once_with(*exc_info)


def test_keyboard_interrupt_is_not_logged(monkeypatch, caplog):
    with installed_hooks(monkeypatch) as (previous, _):
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)

    assert _critical_records(caplog) == []
    previous.assert_called_once()


def test_installing_twice_logs_once(monkeypatch, caplog):
    with installed_hooks(monkeypatch):
        lm.install_exception_hooks()
        sys.excepthook(ValueError, ValueError("once"), None)

    assert len(_critical_records(caplog)) == 1


def test_enable_crash_handler_writes_a_per_service_header(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "_get_log_dir", lambda: str(tmp_path))
    monkeypatch.setattr(lm.faulthandler, "enable", MagicMock())
    monkeypatch.setattr(lm, "install_exception_hooks", MagicMock())
    monkeypatch.setattr(lm, "SERVICE_ID", "")

    lm.enable_crash_handler("ACQ_1")
    lm._crash_log_file.close()

    data = (tmp_path / "neurobooth_crash_ACQ_1.log").read_bytes()
    [header] = lm.CRASH_LOG_HEADER_PATTERN.finditer(data)
    assert header.group("service_id") == b"ACQ_1"
    assert lm.SERVICE_ID == "ACQ_1"
    lm.install_exception_hooks.assert_called_once()


def test_db_fallback_file_is_per_service(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "_get_log_dir", lambda: str(tmp_path))

    assert lm.db_fallback_log_path("STM").name == "neurobooth_db_log_fallback_STM.log"
    assert lm.db_fallback_log_path("").name == "neurobooth_db_log_fallback.log"


# --- Crash-log backfill ------------------------------------------------------


def _header(pid: int, service_id: str = "ACQ_0") -> str:
    return lm.CRASH_LOG_HEADER.format(service_id=service_id, started="2026-10-14T09:00:00", pid=pid)


TRACE = "Windows fatal exception: access violation\n\nThread 0x1 (most recent call first):\n  File \"warble.py\", line 3"


@pytest.fixture
def crash_log(tmp_path):
    return tmp_path / "neurobooth_crash_ACQ_0.log"


def _messages(caplog):
    return [r.getMessage() for r in caplog.records]


def test_crash_backfill_logs_earlier_traces_and_skips_own_block(crash_log, monkeypatch, caplog):
    monkeypatch.setattr(sm.os, "getpid", lambda: 300)
    # enable_crash_handler writes in text mode, so on Windows lines end in CRLF.
    crash_log.write_bytes(
        (
            f"\n{_header(100)}\n{TRACE}\n"
            f"\n{_header(200)}\n"  # clean launch: header only
            f"\n{_header(300)}\n"  # this process
        ).replace("\n", "\r\n").encode()
    )
    logger = logging.getLogger("test_crash_backfill")

    with caplog.at_level(logging.ERROR, logger="test_crash_backfill"):
        assert sm.backfill_crash_log(crash_log, logger) == 1

    [message] = _messages(caplog)
    assert "PID 100" in message and "access violation" in message
    assert caplog.records[0].device == "crash_log"


def test_crash_backfill_resumes_at_own_header_on_next_launch(crash_log, monkeypatch, caplog):
    logger = logging.getLogger("test_crash_backfill")
    monkeypatch.setattr(sm.os, "getpid", lambda: 300)
    crash_log.write_text(f"\n{_header(100)}\n{TRACE}\n\n{_header(300)}\n")
    sm.backfill_crash_log(crash_log, logger)
    assert sm.backfill_crash_log(crash_log, logger) == 0  # nothing new

    # This process crashes after its backfill, then the service relaunches.
    with crash_log.open("a") as crash_file:
        crash_file.write(f"Fatal Python error: Aborted\n\n{_header(400)}\n")
    monkeypatch.setattr(sm.os, "getpid", lambda: 400)
    caplog.clear()

    with caplog.at_level(logging.ERROR, logger="test_crash_backfill"):
        assert sm.backfill_crash_log(crash_log, logger) == 1
    assert "PID 300" in _messages(caplog)[0] and "Aborted" in _messages(caplog)[0]


def test_crash_backfill_restarts_when_log_was_truncated(crash_log, monkeypatch):
    monkeypatch.setattr(sm.os, "getpid", lambda: 300)
    crash_log.write_text(f"\n{_header(100)}\n{TRACE}\n\n{_header(300)}\n")
    (crash_log.parent / f"{crash_log.name}.offset").write_text("999999")

    assert sm.backfill_crash_log(crash_log, logging.getLogger("t")) == 1


def test_crash_backfill_without_log_does_nothing(crash_log):
    assert sm.backfill_crash_log(crash_log, logging.getLogger("t")) == 0


# --- DB-fallback-log backfill ------------------------------------------------


@pytest.fixture
def fallback_log(tmp_path):
    return tmp_path / "neurobooth_db_log_fallback_ACQ_0.log"


def test_fallback_backfill_relogs_warnings_and_summarizes_the_rest(fallback_log, caplog):
    fallback_log.write_text(
        "[2026-10-14T09:00:00] DEBUG lsl.py:10 start> noisy  (DB log write failed: x)\n"
        "[2026-10-14T09:00:01] ERROR flir.py:20 save> disk full  (DB log write failed: x)\n"
        "Traceback (most recent call last):\n  File \"flir.py\", line 20\nOSError: disk full\n"
        "[2026-10-14T09:00:02] WARNING mbient.py:30 connect> retrying  (DB log write failed: x)\n"
    )
    logger = logging.getLogger("test_fallback_backfill")

    with caplog.at_level(logging.DEBUG, logger="test_fallback_backfill"):
        assert sm.backfill_db_fallback_log(fallback_log, logger) == 2

    error, warning, summary = caplog.records
    assert error.levelno == logging.ERROR and "OSError: disk full" in error.getMessage()
    assert warning.levelno == logging.WARNING and "retrying" in warning.getMessage()
    assert "1 further records" in summary.getMessage()

    caplog.clear()
    assert sm.backfill_db_fallback_log(fallback_log, logger) == 0  # offset saved
    assert caplog.records == []


def test_fallback_backfill_is_capped(fallback_log, monkeypatch, caplog):
    monkeypatch.setattr(sm, "MAX_RECOVERED_RECORDS", 2)
    fallback_log.write_text("".join(f"[t] ERROR a.py:1 f> error {i}  (x)\n" for i in range(5)))
    logger = logging.getLogger("test_fallback_backfill")

    with caplog.at_level(logging.DEBUG, logger="test_fallback_backfill"):
        assert sm.backfill_db_fallback_log(fallback_log, logger) == 2
    assert "3 further records" in caplog.records[-1].getMessage()


# --- Heartbeat ---------------------------------------------------------------


@pytest.fixture
def connections(monkeypatch):
    """Record every connection ``ServiceHeartbeat`` opens."""
    opened = []

    def fake_get_conn(*args, **kwargs):
        conn = MagicMock(name=f"conn{len(opened)}")
        opened.append(conn)
        return conn

    monkeypatch.setattr(sm.metadator, "get_database_connection", fake_get_conn)
    monkeypatch.setattr(lm, "SESSION_ID", "100123_2026-10-14")
    return opened


def _executed(conn):
    cursor = conn.cursor.return_value.__enter__.return_value
    return [call.args for call in cursor.execute.call_args_list]


def test_heartbeat_upserts_then_marks_clean_stop(connections):
    heartbeat = sm.ServiceHeartbeat("STM", interval_sec=60)
    heartbeat.start()  # first beat is immediate
    heartbeat.stop(exit_code=0)

    [conn] = connections
    (upsert, beat_args), (stop, stop_args) = _executed(conn)
    assert upsert.startswith("INSERT INTO service_heartbeat")
    assert beat_args["service_id"] == "STM"
    assert beat_args["session_id"] == "100123_2026-10-14"
    assert stop.startswith("UPDATE service_heartbeat") and stop_args["exit_code"] == 0
    assert stop_args["process_start"] == beat_args["process_start"]
    conn.close.assert_called_once()
    assert conn.autocommit is True


def test_heartbeat_warns_once_per_outage_and_reconnects(connections, monkeypatch, caplog):
    heartbeat = sm.ServiceHeartbeat("ACQ_0")
    heartbeat._beat()
    connections[0].cursor.side_effect = Exception("server closed the connection")
    reconnect = sm.metadator.get_database_connection

    with caplog.at_level(logging.INFO, logger=lm.APP_LOG_NAME):
        heartbeat._beat()  # fails on the held connection
        monkeypatch.setattr(
            sm.metadator, "get_database_connection", MagicMock(side_effect=Exception("down"))
        )
        heartbeat._beat()  # reconnect fails too
        heartbeat._beat()
        monkeypatch.setattr(sm.metadator, "get_database_connection", reconnect)
        heartbeat._beat()  # recovers on a fresh connection

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert caplog.records[-1].getMessage() == "Service heartbeat writes recovered."
    connections[0].close.assert_called_once()


def test_start_service_monitor_survives_a_backfill_failure(connections, monkeypatch, caplog):
    monkeypatch.setattr(sm, "backfill_crash_log", MagicMock(side_effect=OSError("locked")))
    monkeypatch.setattr(lm, "_get_log_dir", lambda: "unused")
    logger = logging.getLogger("test_start_service_monitor")

    with caplog.at_level(logging.ERROR, logger="test_start_service_monitor"):
        heartbeat = sm.start_service_monitor("CTR", logger)
    heartbeat.stop(exit_code=1)

    assert "Crash-log backfill failed for CTR." in _messages(caplog)
    assert _executed(connections[0])[-1][1]["exit_code"] == 1
