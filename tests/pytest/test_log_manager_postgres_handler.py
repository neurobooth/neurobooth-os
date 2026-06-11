"""Resilience tests for ``PostgreSQLHandler`` (log_manager).

The handler must not silently drop logs on a DB problem: it should reconnect a
broken connection and retry, and fall back to a local file when the DB is still
unreachable. Regression coverage for the all-day logging blackout where a single
dropped DB connection killed logging for the rest of a process's life and emit
only ``print()``'d to a hidden console.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

import neurobooth_os.log_manager as lm


def _record(msg: str = "boom") -> logging.LogRecord:
    return logging.LogRecord(
        name="app", level=logging.ERROR, pathname=__file__, lineno=10,
        msg=msg, args=(), exc_info=None,
    )


@pytest.fixture
def handler(monkeypatch, tmp_path):
    """A ``PostgreSQLHandler`` wired to mock DB connections and a temp log dir."""
    monkeypatch.setattr(lm.config, "get_server_name_from_env", lambda: "ACQ")
    monkeypatch.setattr(lm, "_get_log_dir", lambda: str(tmp_path))

    conns = []

    def fake_get_conn():
        conn = MagicMock(name=f"conn{len(conns)}")
        conn.cursor.return_value = MagicMock(name="cursor")
        conns.append(conn)
        return conn

    monkeypatch.setattr(lm.metadator, "get_database_connection", fake_get_conn)
    h = lm.PostgreSQLHandler(logging.DEBUG)
    h._reconnect_interval_sec = 0.0  # don't rate-limit reconnects in tests
    h._conns = conns
    return h


def test_emit_happy_path_inserts(handler):
    handler.emit(_record())
    handler.cursor.execute.assert_called_once()


def test_emit_reconnects_on_broken_cursor(handler, tmp_path):
    handler.cursor.execute.side_effect = Exception("connection closed")

    handler.emit(_record("after-drop"))

    # A fresh connection was built and the row landed on it; nothing lost.
    assert len(handler._conns) == 2
    handler._conns[1].cursor.return_value.execute.assert_called_once()
    assert not (tmp_path / "neurobooth_db_log_fallback.log").exists()


def test_emit_falls_back_to_file_when_db_down(handler, monkeypatch, tmp_path):
    handler.cursor.execute.side_effect = Exception("db down")
    monkeypatch.setattr(
        lm.metadator, "get_database_connection",
        MagicMock(side_effect=Exception("cannot connect")),
    )

    handler.emit(_record("must-not-be-lost"))

    fallback = tmp_path / "neurobooth_db_log_fallback.log"
    assert fallback.exists()
    assert "must-not-be-lost" in fallback.read_text()


def test_emit_never_raises(handler, monkeypatch):
    # Even if building the row blows up, emit must not propagate.
    monkeypatch.setattr(
        handler, "_build_args", MagicMock(side_effect=Exception("kaboom")))
    handler.emit(_record())  # must not raise
