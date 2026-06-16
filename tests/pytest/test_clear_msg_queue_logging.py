"""Tests for capturing message_queue contents before the GUI clears it (issue #706).

``clear_msg_queue`` wipes the table at the start of each session. Because the queue is
only cleared here, a normal prior session leaves hundreds of already-read rows behind --
so the forensic signal is the *unread* rows (messages never consumed), not mere presence.
These tests confirm unread messages are logged at WARNING (and only the unread ones are
dumped) before the delete, while all-consumed leftovers stay quiet -- with no database
(the connection, ``Table``, and the snapshot SELECT are stubbed).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

import neurobooth_os.iout.metadator as meta
import neurobooth_os.log_manager as lm


def _row(uuid: str, age: float, unread: bool = True, dest: str = "STM",
         msg_type: str = "CreateTasksRequest") -> meta.MessageQueueRow:
    return meta.MessageQueueRow(
        id=1, uuid=uuid, msg_type=msg_type, priority=0, source="CTR",
        destination=dest, time_created=datetime(2026, 1, 1),
        time_read=None if unread else datetime(2026, 1, 1),
        age_seconds=age, unread=unread, body='{"task_id": "DSC"}',
    )


@pytest.fixture
def fake_table(monkeypatch):
    """Replace neurobooth_terra.Table so delete_row() never touches a database."""
    table = MagicMock(name="message_queue_table")
    monkeypatch.setattr(meta, "Table", lambda *a, **k: table)
    return table


def test_snapshot_maps_rows_and_serializes_jsonb_body():
    cursor = MagicMock()
    cursor.description = [
        (c,) for c in (
            "id", "uuid", "msg_type", "priority", "source", "destination",
            "time_created", "time_read", "age_seconds", "unread", "body",
        )
    ]
    cursor.fetchall.return_value = [
        (1, "u1", "CreateTasksRequest", 0, "CTR", "STM",
         datetime(2026, 1, 1), None, 120.0, True, {"task_id": "DSC"}),
    ]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    rows = meta.snapshot_message_queue(conn)

    assert len(rows) == 1
    r = rows[0]
    assert (r.destination, r.msg_type, r.unread, r.age_seconds) == ("STM", "CreateTasksRequest", True, 120.0)
    assert r.body == '{"task_id": "DSC"}'  # JSONB dict serialized back to a string
    cursor.close.assert_called_once()


def test_format_rows_empty_and_populated():
    assert meta.format_message_queue_rows([]) == "<message_queue empty>"

    text = meta.format_message_queue_rows([_row("u1", age=90.0)])
    assert "1 row(s), 1 unread" in text
    assert "UNREAD" in text
    assert "CreateTasksRequest" in text


def test_format_rows_truncates_long_body():
    big = _row("u1", age=5.0)
    object.__setattr__(big, "body", "x" * 1000)  # frozen dataclass
    text = meta.format_message_queue_rows([big], body_max_len=50)
    assert "...(truncated)" in text
    assert "x" * 1000 not in text


def test_clear_logs_contents_before_deleting(monkeypatch, fake_table):
    events = []
    monkeypatch.setattr(
        meta, "snapshot_message_queue",
        lambda conn: (events.append("snapshot"), [_row("u1", age=120.0)])[1],
    )
    app_log = MagicMock()
    app_log.warning.side_effect = lambda *a, **k: events.append("log")
    monkeypatch.setattr(lm, "APP_LOGGER", app_log)
    fake_table.delete_row.side_effect = lambda *a, **k: events.append("delete")

    meta.clear_msg_queue(MagicMock())

    # Snapshot first, log next, delete last -- "copy messages to log before clearing".
    assert events[0] == "snapshot"
    assert events[-1] == "delete"
    assert "log" in events
    logged = " ".join(str(c) for c in app_log.warning.call_args_list)
    assert "CreateTasksRequest" in logged  # the pending message is in the log


def test_clear_empty_queue_is_quiet_but_still_deletes(monkeypatch, fake_table):
    monkeypatch.setattr(meta, "snapshot_message_queue", lambda conn: [])
    app_log = MagicMock()
    monkeypatch.setattr(lm, "APP_LOGGER", app_log)

    meta.clear_msg_queue(MagicMock())

    app_log.warning.assert_not_called()  # no noise on a clean start
    app_log.debug.assert_called_once()
    fake_table.delete_row.assert_called_once()


def test_clear_falls_back_to_module_logger_when_app_logger_absent(monkeypatch, fake_table):
    # Before make_db_logger() runs, APP_LOGGER is None; clearing must still work.
    monkeypatch.setattr(meta, "snapshot_message_queue", lambda conn: [_row("u1", age=90.0)])
    monkeypatch.setattr(lm, "APP_LOGGER", None)

    meta.clear_msg_queue(MagicMock())  # must not raise

    fake_table.delete_row.assert_called_once()


def test_clear_still_deletes_when_snapshot_fails(monkeypatch, fake_table):
    # The capture is best-effort; a broken snapshot must not block the clear, and the
    # connection is rolled back so the delete isn't poisoned by an aborted transaction.
    monkeypatch.setattr(
        meta, "snapshot_message_queue",
        MagicMock(side_effect=RuntimeError("SELECT blew up")),
    )
    app_log = MagicMock()
    monkeypatch.setattr(lm, "APP_LOGGER", app_log)
    conn = MagicMock()

    meta.clear_msg_queue(conn)  # must not raise

    fake_table.delete_row.assert_called_once()  # essential op still ran
    conn.rollback.assert_called_once()
    app_log.exception.assert_called_once()


def test_clear_all_read_rows_is_quiet_no_halt_warning(monkeypatch, fake_table):
    # Normal end-of-session leftovers: rows present but all consumed. Must NOT warn --
    # the calibration bug was crying "may have halted" on every session's read leftovers.
    monkeypatch.setattr(
        meta, "snapshot_message_queue",
        lambda conn: [_row("a", age=300.0, unread=False),
                      _row("b", age=250.0, unread=False)],
    )
    app_log = MagicMock()
    monkeypatch.setattr(lm, "APP_LOGGER", app_log)

    meta.clear_msg_queue(MagicMock())

    app_log.warning.assert_not_called()   # no false halt/unconsumed warning
    app_log.debug.assert_called_once()    # logged quietly at DEBUG instead
    fake_table.delete_row.assert_called_once()


def test_clear_warns_and_dumps_only_unread_rows(monkeypatch, fake_table):
    # When the prior session left messages unconsumed, warn and dump *only* the unread
    # rows -- the consumed rows are normal accumulation and would just be noise.
    monkeypatch.setattr(
        meta, "snapshot_message_queue",
        lambda conn: [_row("read1", age=300.0, unread=False, msg_type="FramePreviewRequest"),
                      _row("stuck", age=250.0, unread=True, msg_type="CreateTasksRequest")],
    )
    app_log = MagicMock()
    monkeypatch.setattr(lm, "APP_LOGGER", app_log)

    meta.clear_msg_queue(MagicMock())

    app_log.warning.assert_called()
    logged = " ".join(str(c) for c in app_log.warning.call_args_list)
    assert "CreateTasksRequest" in logged       # the unread message is surfaced
    assert "FramePreviewRequest" not in logged  # the consumed one is not dumped
    fake_table.delete_row.assert_called_once()
