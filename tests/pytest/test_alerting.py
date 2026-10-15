"""Unit tests for neurobooth_os/alerting.py.

The SQL in ``PostgresAlertStore`` is not exercised here (no database in the unit
suite); ``run_once`` is driven through an in-memory store with the same interface.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

import pytest

import neurobooth_os.alerting as ba
from neurobooth_os.config import AlertingSpec, NeuroboothConfig

EASTERN = timezone(timedelta(hours=-4))
T0 = datetime(2026, 10, 14, 9, 0, 0, tzinfo=EASTERN)
SUBJECT = "100123"
SESSION = f"{SUBJECT}_2026-10-14"


def log_row(
    message: str = "Mbient F7 failed to connect after 3 attempts",
    *,
    at: datetime = T0,
    server_type: str = "ACQ_0",
    server_id: str = "ACQ0-PC",
    filename: str = "mbient.py",
    line_no: int = 412,
    device: Optional[str] = None,
    traceback: Optional[str] = None,
    level: str = "error",
) -> ba.LogRow:
    return ba.LogRow(
        server_time=at,
        server_type=server_type,
        server_id=server_id,
        log_level=level,
        device=device,
        filename=filename,
        function="connect",
        line_no=line_no,
        message=message,
        traceback=traceback,
        subject_id=SUBJECT,
    )


# --- Scrubbing ------------------------------------------------------------------------


def test_scrub_removes_session_names_inside_paths():
    text = rf"Could not write D:\neurobooth\data\{SESSION}_task_obs_1\x.xdf"
    assert (
        ba.Scrubber([]).scrub(text)
        == r"Could not write D:\neurobooth\data\<session>_task_obs_1\x.xdf"
    )


def test_scrub_removes_known_and_row_subject_ids_as_whole_tokens_only():
    scrubber = ba.Scrubber(["ab12"])
    scrubbed = scrubber.scrub(
        "subject AB12 and 100123 at port 1001234", extra_subject_ids=[SUBJECT]
    )
    assert scrubbed == "subject <subject> and <subject> at port 1001234"


def test_normalize_replaces_values_that_vary_between_occurrences():
    normalized = ba.normalize_message(
        "Timeout  after 30.5 s at 0x7FFE12 (id 3f2504e0-4f89-11d3-9a0c-0305e82c3301)"
    )
    assert normalized == "Timeout after <n>.<n> s at <hex> (id <uuid>)"


# --- Fingerprints ---------------------------------------------------------------------


def test_same_failure_with_different_numbers_shares_a_fingerprint():
    scrubber = ba.Scrubber([])
    first = ba.occurrence_from_log_row(
        log_row("Mbient F7 failed after 3 attempts"), scrubber
    )
    second = ba.occurrence_from_log_row(
        log_row("Mbient F7 failed after 5 attempts"), scrubber
    )
    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize(
    "change",
    [
        {"server_id": "ACQ1-PC"},
        {"server_type": "STM"},
        {"line_no": 413},
        {"filename": "flir.py"},
    ],
)
def test_machine_service_and_location_are_part_of_the_fingerprint(change):
    scrubber = ba.Scrubber([])
    assert (
        ba.occurrence_from_log_row(log_row(), scrubber).fingerprint
        != ba.occurrence_from_log_row(log_row(**change), scrubber).fingerprint
    )


CRASH_MESSAGE = (
    "Crash trace recovered from neurobooth_crash_ACQ_0.log (ACQ_0 launched 2026-10-14 08:00, PID 4242):\n"
    "Windows fatal exception: access violation\n"
    "\n"
    "Thread 0x00001a2c (most recent call first):\n"
    '  File "C:\\neurobooth\\neurobooth_os\\iout\\flir.py", line 88 in record\n'
    "\n"
    "Current thread 0x00003b10 (most recent call first):\n"
    '  File "C:\\neurobooth\\neurobooth_os\\iout\\mbient.py", line 296 in reconnect\n'
    '  File "C:\\neurobooth\\neurobooth_os\\iout\\mbient.py", line 120 in run\n'
)


def test_crash_log_row_uses_the_crashing_threads_innermost_frame():
    row = log_row(
        CRASH_MESSAGE,
        device=ba.DEVICE_CRASH_LOG,
        filename="service_monitor.py",
        line_no=190,
    )
    occurrence = ba.occurrence_from_log_row(row, ba.Scrubber([]))
    assert occurrence.location == "mbient.py:296"
    assert occurrence.normalized_message == "Windows fatal exception: access violation"
    assert "Current thread" in occurrence.sample_traceback


def test_db_fallback_row_uses_the_original_records_location_and_message():
    message = (
        "Recovered from neurobooth_db_log_fallback_STM.log: "
        f"[2026-10-14T08:59:58.120000] ERROR task.py:77 present> Task failed for {SESSION}  "
        "(DB log write failed: server closed the connection (unexpectedly))\n"
        'Traceback (most recent call last):\n  File "task.py", line 77\nValueError: bad frame\n'
    )
    row = log_row(
        message,
        device=ba.DEVICE_DB_FALLBACK_LOG,
        filename="service_monitor.py",
        line_no=240,
    )
    occurrence = ba.occurrence_from_log_row(row, ba.Scrubber([]))
    assert occurrence.location == "task.py:77"
    assert occurrence.sample_message == "Task failed for <session>"
    assert occurrence.sample_traceback.endswith("ValueError: bad frame")


def test_every_death_of_a_service_on_a_machine_shares_a_fingerprint():
    first = ba.occurrence_from_dead_service(
        ba.DeadServiceRow("ACQ_0", "ACQ0-PC", 11, T0, "v0.96.0")
    )
    second = ba.occurrence_from_dead_service(
        ba.DeadServiceRow("ACQ_0", "ACQ0-PC", 12, T0 + timedelta(hours=1), "v0.96.0")
    )
    other = ba.occurrence_from_dead_service(
        ba.DeadServiceRow("STM", "ACQ0-PC", 13, T0, "v0.96.0")
    )
    assert first.fingerprint == second.fingerprint != other.fingerprint
    assert first.kind == ba.KIND_DEAD_SERVICE


# --- Dedup ----------------------------------------------------------------------------


def occurrence(at: datetime = T0) -> ba.Occurrence:
    return ba.occurrence_from_log_row(log_row(at=at), ba.Scrubber([]))


def test_new_fingerprint_alerts():
    changed, alerts = ba.merge_occurrences({}, [occurrence()], T0)
    [alert] = alerts
    assert alert.reason == ba.REASON_NEW
    assert alert.record.count == 1 and alert.record.notify_count == 1
    assert changed == [alert.record]


def test_unacknowledged_repeat_is_counted_but_not_alerted():
    [record], _ = ba.merge_occurrences({}, [occurrence()], T0)
    changed, alerts = ba.merge_occurrences(
        {record.fingerprint: record}, [occurrence(T0 + timedelta(minutes=5))], T0
    )
    assert alerts == []
    assert changed[0].count == 2
    assert changed[0].last_seen == T0 + timedelta(minutes=5)


def test_repeat_after_acknowledgement_alerts_and_reopens():
    [record], _ = ba.merge_occurrences({}, [occurrence()], T0)
    acked = replace(record, acknowledged=True, acknowledged_by="spencer")
    changed, [alert] = ba.merge_occurrences(
        {acked.fingerprint: acked}, [occurrence(T0 + timedelta(days=2))], T0
    )
    assert alert.reason == ba.REASON_RECURRED
    assert alert.record.acknowledged is False
    assert alert.record.acknowledged_by == "spencer"
    assert alert.record.count == 2 and alert.record.notify_count == 2


def test_rows_already_counted_by_an_overlapping_read_are_skipped():
    [record], _ = ba.merge_occurrences({}, [occurrence()], T0)
    changed, alerts = ba.merge_occurrences(
        {record.fingerprint: record}, [occurrence(T0)], T0
    )
    assert changed == [] and alerts == []


def test_burst_in_one_run_alerts_once_with_its_count():
    burst = [occurrence(T0 + timedelta(seconds=offset)) for offset in range(5)]
    [record], [alert] = ba.merge_occurrences({}, burst, T0)
    assert alert.occurrences_this_run == 5
    assert record.count == 5 and record.first_seen == T0


# --- Notifications --------------------------------------------------------------------


def test_notification_never_contains_subject_or_session_ids():
    rows = [
        log_row(
            f"Lost frames for {SESSION} (subject {SUBJECT})",
            traceback=f"File D:\\data\\{SESSION}\\x.py",
        ),
        log_row(
            CRASH_MESSAGE.replace("mbient.py", f"{SUBJECT}.py"),
            device=ba.DEVICE_CRASH_LOG,
        ),
    ]
    alerts = ba.merge_occurrences(
        {}, [ba.occurrence_from_log_row(r, ba.Scrubber([])) for r in rows], T0
    )[1]
    subject, body = ba.format_notification(alerts, "Neurobooth test")
    for text in (subject, body):
        assert SUBJECT not in text
    assert "2 new booth failures" in subject
    assert "python -m neurobooth_os.alerting ack" in body


def test_teams_payload_truncates_long_bodies():
    payload = ba.TeamsWorkflowSender.payload(
        "subject", "x" * (ba.TEAMS_MAX_BODY_CHARS + 50)
    )
    text = payload["attachments"][0]["content"]["body"][1]["text"]
    assert len(text) < ba.TEAMS_MAX_BODY_CHARS + 100
    assert text.endswith("(truncated; see alert_history)")


class RecordingSender:
    def __init__(self, error: Optional[Exception] = None):
        self.sent: List[tuple] = []
        self.error = error

    def send(self, subject: str, body: str) -> None:
        self.sent.append((subject, body))
        if self.error is not None:
            raise self.error


def test_multi_sender_tries_every_channel_then_raises():
    failing, working = RecordingSender(OSError("relay down")), RecordingSender()
    with pytest.raises(RuntimeError, match="1 of 2"):
        ba.MultiSender([failing, working]).send("s", "b")
    assert len(working.sent) == 1


def test_multi_sender_requires_a_channel():
    with pytest.raises(ValueError):
        ba.MultiSender([])


# --- run_once -------------------------------------------------------------------------


class InMemoryStore:
    def __init__(
        self,
        now: datetime,
        log_rows: Sequence[ba.LogRow] = (),
        dead: Sequence[ba.DeadServiceRow] = (),
    ):
        self.current_time = now
        self.log_rows = list(log_rows)
        self.dead = list(dead)
        self.history: Dict[str, ba.AlertRecord] = {}
        self.watermark: Optional[datetime] = None
        self.last_run_at: Optional[datetime] = None
        self.fetched_since: List[datetime] = []
        self.locked_by_another = False

    def try_lock(self) -> bool:
        return not self.locked_by_another

    def now(self) -> datetime:
        return self.current_time

    def get_log_watermark(self) -> Optional[datetime]:
        return self.watermark

    def fetch_log_rows(self, since: datetime) -> List[ba.LogRow]:
        self.fetched_since.append(since)
        return [row for row in self.log_rows if row.server_time > since]

    def fetch_dead_services(
        self, stale_after: timedelta, max_age: timedelta
    ) -> List[ba.DeadServiceRow]:
        return [
            row
            for row in self.dead
            if self.current_time - max_age
            < row.last_beat
            < self.current_time - stale_after
        ]

    def fetch_subject_ids(self) -> List[str]:
        return [SUBJECT]

    def load_history(self, fingerprints: Sequence[str]) -> Dict[str, ba.AlertRecord]:
        return {fp: self.history[fp] for fp in fingerprints if fp in self.history}

    def save_history(self, records: Sequence[ba.AlertRecord]) -> None:
        self.history.update({record.fingerprint: record for record in records})

    def save_state(self, log_watermark: datetime, run_at: datetime) -> None:
        self.watermark, self.last_run_at = log_watermark, run_at


SETTINGS = AlertingSpec(label="Neurobooth test")


def test_run_sends_one_notification_for_errors_and_dead_services():
    now = T0 + timedelta(minutes=10)
    store = InMemoryStore(
        now,
        log_rows=[
            log_row(at=T0),
            log_row(at=T0 + timedelta(seconds=1)),
            log_row("STM froze", server_type="STM", at=T0),
        ],
        dead=[ba.DeadServiceRow("CTR", "CTR-PC", 7, T0, "v0.96.0")],
    )
    sender = RecordingSender()
    alerts = ba.run_once(store, sender, SETTINGS)
    assert len(alerts) == 3
    [(subject, body)] = sender.sent
    assert "3 new booth failures" in subject
    assert "Service died" in body
    assert store.watermark == T0 + timedelta(seconds=1)
    assert store.fetched_since == [now - timedelta(hours=24) - timedelta(minutes=60)]


def test_second_run_over_the_same_rows_is_quiet():
    store = InMemoryStore(
        T0 + timedelta(minutes=10),
        log_rows=[log_row()],
        dead=[ba.DeadServiceRow("CTR", "CTR-PC", 7, T0, None)],
    )
    ba.run_once(store, RecordingSender(), SETTINGS)
    sender = RecordingSender()
    store.current_time += timedelta(minutes=1)
    assert ba.run_once(store, sender, SETTINGS) == []
    assert sender.sent == []
    assert all(record.count == 1 for record in store.history.values())


def test_watermark_never_moves_past_now():
    now = T0
    store = InMemoryStore(
        now, log_rows=[log_row(at=T0 + timedelta(hours=3))]
    )  # booth clock ahead
    ba.run_once(store, RecordingSender(), SETTINGS)
    assert store.watermark == now


def test_failed_send_propagates_so_the_caller_rolls_back():
    store = InMemoryStore(T0 + timedelta(minutes=1), log_rows=[log_row()])
    with pytest.raises(OSError):
        ba.run_once(store, RecordingSender(OSError("relay down")), SETTINGS)


def test_run_is_skipped_while_another_alerter_holds_the_lock():
    store = InMemoryStore(T0 + timedelta(minutes=1), log_rows=[log_row()])
    store.locked_by_another = True
    sender = RecordingSender()
    assert ba.run_once(store, sender, SETTINGS) == []
    assert sender.sent == [] and store.history == {} and store.watermark is None


def test_alerting_settings_come_from_the_neurobooth_config():
    spec = NeuroboothConfig.model_fields["alerting"]
    assert spec.default is None  # configs without the section still load
    settings = AlertingSpec(
        label="Neurobooth Wang",
        smtp={"host": "relay", "sender": "a@x.org", "recipients": ["b@x.org"]},
        teams_webhook_url="https://example.invalid/flow",
    )
    assert "flow" not in repr(settings)  # the URL is a secret
    sender = ba.make_sender(settings)
    assert [type(s) for s in sender.senders] == [ba.SmtpSender, ba.TeamsWorkflowSender]


def test_alerting_settings_need_a_channel():
    with pytest.raises(ValueError):
        ba.make_sender(SETTINGS)
