"""Notify the team when a booth service (CTR, STM, ACQ_n) logs an error or dies.

Runs on each environment's CTR machine every minute, as a Task Scheduler entry
(``extras/register_alerter_task.bat``), against that environment's database. Each run:

1. Reads ``log_application`` rows at level error/critical since the last run, and
   ``service_heartbeat`` rows whose process stopped beating without a clean shutdown.
2. Reduces each one to a fingerprint: service + machine + source location + normalized
   message.
3. Folds them into ``alert_history`` and sends one notification listing every
   fingerprint that is new, or that recurred after someone acknowledged it.

Subject and session IDs never leave the database: they are scrubbed from every message
and traceback before it is stored in ``alert_history`` or sent. See
``docs/booth_alerting.md`` for the design and ``sql/migration/booth_alerts_v0.96.0.sql``
for the tables. Settings come from the ``alerting`` section of the neurobooth config.

Usage:
    python -m neurobooth_os.alerting run
    python -m neurobooth_os.alerting list [--all]
    python -m neurobooth_os.alerting ack FINGERPRINT --by NAME
    python -m neurobooth_os.alerting test-notify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import smtplib
import sys
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

import neurobooth_os.config as cfg
import neurobooth_os.log_manager as log_manager
from neurobooth_os.config import AlertingSpec, SmtpSpec
from neurobooth_os.iout import metadator

LOGGER = logging.getLogger("booth_alerter")

# Arbitrary constant naming the PostgreSQL advisory lock that lets only one alerter run
# against a database at a time (staging and production share the CTR machines).
ADVISORY_LOCK_KEY = 0x4E42414C

KIND_LOG = "log"
KIND_DEAD_SERVICE = "dead_service"

REASON_NEW = "new"
REASON_RECURRED = "recurred after acknowledgement"

# Set by neurobooth_os/service_monitor.py on rows it backfills from local files.
DEVICE_CRASH_LOG = "crash_log"
DEVICE_DB_FALLBACK_LOG = "db_fallback_log"

MAX_NORMALIZED_MESSAGE_CHARS = 300
MAX_SAMPLE_MESSAGE_CHARS = 2000
TRACEBACK_TAIL_LINES = 25
TEAMS_MAX_BODY_CHARS = 20000

# --- Scrubbing and normalization ------------------------------------------------------

# Session names are "<subject_id>_<YYYY-MM-DD>" (server_stm.py: subject_id_date), and they
# appear inside data-folder paths, so the match can't rely on word boundaries.
_SESSION_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]+_\d{4}-\d{2}-\d{2}(?!\d)")
_HEX_PATTERN = re.compile(r"0x[0-9A-Fa-f]+")
_UUID_PATTERN = re.compile(
    r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b"
)
_NUMBER_PATTERN = re.compile(r"\d+")
_WHITESPACE_PATTERN = re.compile(r"\s+")

SESSION_PLACEHOLDER = "<session>"
SUBJECT_PLACEHOLDER = "<subject>"


class Scrubber:
    """Removes subject and session IDs from text before it is stored or sent."""

    def __init__(self, subject_ids: Iterable[str]):
        """Build the scrubber.

        Args:
            subject_ids: Every known subject ID, normally the ``subject`` table's keys.
        """
        self._known_ids = {
            subject_id.strip() for subject_id in subject_ids if subject_id
        }
        self._known_ids.discard("")
        self._pattern = self._compile(self._known_ids)

    @staticmethod
    def _compile(subject_ids: Iterable[str]) -> Optional[re.Pattern]:
        ordered = sorted(subject_ids, key=len, reverse=True)
        if not ordered:
            return None
        alternatives = "|".join(re.escape(subject_id) for subject_id in ordered)
        return re.compile(
            rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9])", re.IGNORECASE
        )

    def scrub(self, text: Optional[str], extra_subject_ids: Sequence[str] = ()) -> str:
        """Replace session names and subject IDs in ``text`` with placeholders.

        Args:
            text: Text to scrub; None is treated as empty.
            extra_subject_ids: IDs to remove in addition to the known ones, e.g. the
                ``subject_id`` column of the row the text came from.

        Returns:
            The scrubbed text.
        """
        if not text:
            return ""
        text = _SESSION_PATTERN.sub(SESSION_PLACEHOLDER, text)
        pattern = self._pattern
        extra = {
            s.strip() for s in extra_subject_ids if s and s.strip()
        } - self._known_ids
        if extra:
            pattern = self._compile(self._known_ids | extra)
        if pattern is not None:
            text = pattern.sub(SUBJECT_PLACEHOLDER, text)
        return text


def normalize_message(text: str) -> str:
    """Reduce a scrubbed message to the part that identifies the failure.

    Addresses, UUIDs and numbers vary between occurrences of the same failure, so they
    are replaced with placeholders; whitespace is collapsed.

    Args:
        text: An already-scrubbed message.

    Returns:
        The normalized message, at most ``MAX_NORMALIZED_MESSAGE_CHARS`` long.
    """
    text = _UUID_PATTERN.sub("<uuid>", text)
    text = _HEX_PATTERN.sub("<hex>", text)
    text = _NUMBER_PATTERN.sub("<n>", text)
    text = _WHITESPACE_PATTERN.sub(" ", text).strip()
    return text[:MAX_NORMALIZED_MESSAGE_CHARS]


def compute_fingerprint(
    kind: str, server_type: str, server_id: str, location: str, normalized_message: str
) -> str:
    """Hash the fields that identify one distinct failure."""
    key = "\x1f".join((kind, server_type, server_id, location, normalized_message))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def _traceback_tail(text: str) -> str:
    lines = text.rstrip().splitlines()
    return "\n".join(lines[-TRACEBACK_TAIL_LINES:])


# --- Source rows and occurrences ------------------------------------------------------


@dataclass(frozen=True)
class LogRow:
    """An error/critical row from ``log_application``.

    ``subject_id`` is read only so it can be scrubbed from the text; it is never stored
    or sent.
    """

    server_time: datetime
    server_type: str
    server_id: str
    log_level: str
    device: Optional[str]
    filename: Optional[str]
    function: Optional[str]
    line_no: Optional[int]
    message: str
    traceback: Optional[str]
    subject_id: Optional[str]


@dataclass(frozen=True)
class DeadServiceRow:
    """A ``service_heartbeat`` row that went stale without a clean shutdown."""

    service_id: str
    server_id: str
    pid: int
    last_beat: datetime
    release_version: Optional[str]


@dataclass(frozen=True)
class Occurrence:
    """One scrubbed, fingerprinted failure, ready to fold into ``alert_history``."""

    fingerprint: str
    kind: str
    server_type: str
    server_id: str
    location: str
    normalized_message: str
    sample_message: str
    sample_traceback: str
    log_level: Optional[str]
    seen_at: datetime


# faulthandler frame: '  File "C:\\...\\mbient.py", line 296 in connect'
_FAULTHANDLER_FRAME = re.compile(
    r'File "(?P<path>[^"]+)", line (?P<line>\d+) in (?P<function>\S+)'
)
# PostgreSQLHandler._fallback_to_file record:
#   [2026-10-14T09:00:00] ERROR mbient.py:123 connect> message  (DB log write failed: ...)
_FALLBACK_RECORD = re.compile(
    r"\] (?P<level>[A-Z]+) (?P<filename>[^\s:]+):(?P<line>\d+) (?P<function>\S+)> "
    r"(?P<message>.*?)  \((?:DB log write failed|log-record build failed).*\)$",
    re.MULTILINE,
)


def _crash_log_failure(message: str) -> Tuple[str, str]:
    """Return (location, headline) for a faulthandler trace logged by the crash backfill.

    The row's own filename/line point at the backfill, not the crash, so the location is
    the innermost frame of the thread that crashed ("Current thread"), or of the first
    thread listed if faulthandler didn't mark one.
    """
    lines = message.splitlines()
    trace_lines = (
        lines[1:] if lines and lines[0].startswith("Crash trace recovered") else lines
    )
    headline = next(
        (line.strip() for line in trace_lines if line.strip()), "crash trace"
    )

    trace = "\n".join(trace_lines)
    current = trace.find("Current thread")
    frame = _FAULTHANDLER_FRAME.search(trace, current if current >= 0 else 0)
    if frame is None:
        frame = _FAULTHANDLER_FRAME.search(trace)
    if frame is None:
        return "unknown", headline
    return f"{_basename(frame.group('path'))}:{frame.group('line')}", headline


def occurrence_from_log_row(row: LogRow, scrubber: Scrubber) -> Occurrence:
    """Scrub and fingerprint a ``log_application`` row.

    Rows backfilled from a crash log or a DB-fallback log carry the backfill's own source
    location, so the original location is parsed out of the message instead.

    Args:
        row: The row to convert.
        scrubber: Removes subject and session IDs.

    Returns:
        The occurrence.
    """
    extra_ids = (row.subject_id,) if row.subject_id else ()
    message = scrubber.scrub(row.message, extra_ids)
    traceback_text = scrubber.scrub(row.traceback, extra_ids)
    location = (
        f"{row.filename or 'unknown'}:{row.line_no if row.line_no is not None else '?'}"
    )
    headline = message

    if row.device == DEVICE_CRASH_LOG:
        location, headline = _crash_log_failure(message)
        # The whole trace is the useful part; keep it as the traceback.
        traceback_text = message
    elif row.device == DEVICE_DB_FALLBACK_LOG:
        record = _FALLBACK_RECORD.search(message)
        if record is not None:
            location = f"{record.group('filename')}:{record.group('line')}"
            headline = record.group("message")
            traceback_text = message[record.end() :].strip() or traceback_text

    normalized = normalize_message(headline)
    return Occurrence(
        fingerprint=compute_fingerprint(
            KIND_LOG, row.server_type, row.server_id, location, normalized
        ),
        kind=KIND_LOG,
        server_type=row.server_type,
        server_id=row.server_id,
        location=location,
        normalized_message=normalized,
        sample_message=headline[:MAX_SAMPLE_MESSAGE_CHARS],
        sample_traceback=_traceback_tail(traceback_text),
        log_level=row.log_level,
        seen_at=row.server_time,
    )


DEAD_SERVICE_MESSAGE = (
    "Stopped sending heartbeats without a clean shutdown: the process crashed, hung, "
    "or lost its database connection."
)


def occurrence_from_dead_service(row: DeadServiceRow) -> Occurrence:
    """Fingerprint a stale heartbeat. Every death of one service on one machine shares a fingerprint."""
    location = "heartbeat"
    return Occurrence(
        fingerprint=compute_fingerprint(
            KIND_DEAD_SERVICE,
            row.service_id,
            row.server_id,
            location,
            DEAD_SERVICE_MESSAGE,
        ),
        kind=KIND_DEAD_SERVICE,
        server_type=row.service_id,
        server_id=row.server_id,
        location=location,
        normalized_message=DEAD_SERVICE_MESSAGE,
        sample_message=(
            f"{DEAD_SERVICE_MESSAGE} PID {row.pid}, release {row.release_version or 'unknown'}, "
            f"last heartbeat {row.last_beat.isoformat(timespec='seconds')}."
        ),
        sample_traceback="",
        log_level=None,
        seen_at=row.last_beat,
    )


# --- Alert history --------------------------------------------------------------------


@dataclass(frozen=True)
class AlertRecord:
    """One ``alert_history`` row."""

    fingerprint: str
    kind: str
    server_type: str
    server_id: str
    location: str
    normalized_message: str
    sample_message: str
    sample_traceback: str
    log_level: Optional[str]
    first_seen: datetime
    last_seen: datetime
    count: int = 1
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    last_notified_at: Optional[datetime] = None
    notify_count: int = 0

    @classmethod
    def from_occurrence(cls, occurrence: Occurrence) -> AlertRecord:
        return cls(
            fingerprint=occurrence.fingerprint,
            kind=occurrence.kind,
            server_type=occurrence.server_type,
            server_id=occurrence.server_id,
            location=occurrence.location,
            normalized_message=occurrence.normalized_message,
            sample_message=occurrence.sample_message,
            sample_traceback=occurrence.sample_traceback,
            log_level=occurrence.log_level,
            first_seen=occurrence.seen_at,
            last_seen=occurrence.seen_at,
        )


@dataclass(frozen=True)
class Alert:
    """A fingerprint that needs a notification this run."""

    reason: str
    record: AlertRecord
    occurrences_this_run: int


def merge_occurrences(
    history: Dict[str, AlertRecord], occurrences: Iterable[Occurrence], now: datetime
) -> Tuple[List[AlertRecord], List[Alert]]:
    """Fold occurrences into the alert history and decide what to notify about.

    A fingerprint alerts when it is new, or when it recurs after being acknowledged
    (which clears the acknowledgement). Other repeats only update the count and samples.
    An occurrence no later than its fingerprint's ``last_seen`` was already counted by an
    earlier run's overlapping read and is skipped. Every fingerprint includes the machine,
    so its ``last_seen`` and new occurrences come from the same clock.

    Args:
        history: Existing records for (at least) the occurrences' fingerprints.
        occurrences: This run's occurrences, in any order.
        now: The run time, recorded as ``last_notified_at`` on alerted records.

    Returns:
        The records that changed, and the alerts to send.
    """
    changed: Dict[str, AlertRecord] = {}
    reasons: Dict[str, str] = {}
    run_counts: Dict[str, int] = {}

    for occurrence in sorted(occurrences, key=lambda o: o.seen_at):
        fingerprint = occurrence.fingerprint
        record = changed.get(fingerprint) or history.get(fingerprint)
        if record is not None and occurrence.seen_at <= record.last_seen:
            continue
        if record is None:
            record = AlertRecord.from_occurrence(occurrence)
            reasons[fingerprint] = REASON_NEW
        else:
            if record.acknowledged:
                reasons.setdefault(fingerprint, REASON_RECURRED)
            record = replace(
                record,
                last_seen=occurrence.seen_at,
                count=record.count + 1,
                sample_message=occurrence.sample_message,
                sample_traceback=occurrence.sample_traceback,
                log_level=occurrence.log_level,
                acknowledged=False,
            )
        changed[fingerprint] = record
        run_counts[fingerprint] = run_counts.get(fingerprint, 0) + 1

    alerts = []
    for fingerprint, reason in reasons.items():
        record = replace(
            changed[fingerprint],
            last_notified_at=now,
            notify_count=changed[fingerprint].notify_count + 1,
        )
        changed[fingerprint] = record
        alerts.append(Alert(reason, record, run_counts[fingerprint]))
    return list(changed.values()), alerts


# --- Notifications --------------------------------------------------------------------


def format_notification(alerts: Sequence[Alert], label: str) -> Tuple[str, str]:
    """Build the subject line and plain-text body for one run's alerts.

    Args:
        alerts: The alerts to report; must not be empty.
        label: Environment name shown in the subject, e.g. ``"Neurobooth production"``.

    Returns:
        (subject, body). Neither contains subject or session IDs: every field comes from
        scrubbed ``alert_history`` columns.
    """
    new_count = sum(1 for alert in alerts if alert.reason == REASON_NEW)
    recurred_count = len(alerts) - new_count
    first = alerts[0].record
    parts = []
    if new_count:
        parts.append(f"{new_count} new")
    if recurred_count:
        parts.append(f"{recurred_count} recurring")
    subject = (
        f"[{label}] {' and '.join(parts)} booth failure{'s' if len(alerts) > 1 else ''}: "
        f"{first.server_type} {first.location}"
    )

    sections = []
    for alert in alerts:
        record = alert.record
        kind = (
            "Service died"
            if record.kind == KIND_DEAD_SERVICE
            else f"{(record.log_level or 'error').upper()} logged"
        )
        lines = [
            f"{kind} ({alert.reason}): {record.server_type} on {record.server_id}, {record.location}",
            f"  Occurrences: {alert.occurrences_this_run} this run, {record.count} total",
            f"  First seen: {record.first_seen.isoformat(timespec='seconds')}",
            f"  Last seen:  {record.last_seen.isoformat(timespec='seconds')}",
            f"  Message: {record.sample_message}",
        ]
        if record.sample_traceback:
            lines.append("  Traceback (last lines):")
            lines.extend(f"    {line}" for line in record.sample_traceback.splitlines())
        lines.append(
            f"  Acknowledge: python -m neurobooth_os.alerting ack {record.fingerprint} --by <name>"
        )
        sections.append("\n".join(lines))

    body = "\n\n".join(sections)
    body += (
        "\n\nRepeats are counted but not re-sent until acknowledged. "
        "Full rows, including the session, are in log_application in this environment's database."
    )
    return subject, body


class Sender(Protocol):
    def send(self, subject: str, body: str) -> None: ...


class SmtpSender:
    """Sends notifications as plain-text email through an SMTP relay."""

    def __init__(self, settings: SmtpSpec):
        self.settings = settings

    def send(self, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.sender
        message["To"] = ", ".join(self.settings.recipients)
        message.set_content(body)
        with smtplib.SMTP(self.settings.host, self.settings.port, timeout=30) as smtp:
            if self.settings.starttls:
                smtp.starttls()
            if self.settings.username:
                password = self.settings.password
                smtp.login(
                    self.settings.username,
                    password.get_secret_value() if password else "",
                )
            smtp.send_message(message)


class TeamsWorkflowSender:
    """Posts notifications to a Teams channel through a Workflows "webhook request" flow.

    Legacy Office 365 connector webhooks (``*.webhook.office.com``) are retired; the URL
    must come from a Workflows flow.
    """

    def __init__(self, url: str):
        self.url = url

    @staticmethod
    def payload(subject: str, body: str) -> dict:
        if len(body) > TEAMS_MAX_BODY_CHARS:
            body = body[:TEAMS_MAX_BODY_CHARS] + "\n... (truncated; see alert_history)"
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": subject,
                                "weight": "Bolder",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": body,
                                "wrap": True,
                                "fontType": "Monospace",
                            },
                        ],
                    },
                }
            ],
        }

    def send(self, subject: str, body: str) -> None:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(self.payload(subject, body)).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Teams workflow returned HTTP {response.status}")


class MultiSender:
    """Sends to every configured channel; raises if any of them failed."""

    def __init__(self, senders: Sequence[Sender]):
        if not senders:
            raise ValueError(
                "Configure at least one notification channel (smtp or teams_webhook_url)."
            )
        self.senders = list(senders)

    def send(self, subject: str, body: str) -> None:
        errors = []
        for sender in self.senders:
            try:
                sender.send(subject, body)
            except Exception as error:
                LOGGER.exception(
                    "Notification through %s failed.", type(sender).__name__
                )
                errors.append(error)
        if errors:
            raise RuntimeError(
                f"{len(errors)} of {len(self.senders)} notification channels failed"
            ) from errors[0]


def make_sender(settings: AlertingSpec) -> MultiSender:
    """Build a sender for every channel configured in ``settings``."""
    senders: List[Sender] = []
    if settings.smtp is not None:
        senders.append(SmtpSender(settings.smtp))
    if settings.teams_webhook_url is not None:
        senders.append(
            TeamsWorkflowSender(settings.teams_webhook_url.get_secret_value())
        )
    return MultiSender(senders)


# --- Storage --------------------------------------------------------------------------


class AlertStore(Protocol):
    def try_lock(self) -> bool: ...
    def now(self) -> datetime: ...
    def get_log_watermark(self) -> Optional[datetime]: ...
    def fetch_log_rows(self, since: datetime) -> List[LogRow]: ...
    def fetch_dead_services(
        self, stale_after: timedelta, max_age: timedelta
    ) -> List[DeadServiceRow]: ...
    def fetch_subject_ids(self) -> List[str]: ...
    def load_history(self, fingerprints: Sequence[str]) -> Dict[str, AlertRecord]: ...
    def save_history(self, records: Sequence[AlertRecord]) -> None: ...
    def save_state(self, log_watermark: datetime, run_at: datetime) -> None: ...


_HISTORY_COLUMNS = (
    "fingerprint",
    "kind",
    "server_type",
    "server_id",
    "location",
    "normalized_message",
    "sample_message",
    "sample_traceback",
    "log_level",
    "first_seen",
    "last_seen",
    "count",
    "acknowledged",
    "acknowledged_at",
    "acknowledged_by",
    "last_notified_at",
    "notify_count",
)


class PostgresAlertStore:
    """``AlertStore`` over a psycopg2 connection. The caller owns the transaction."""

    def __init__(self, connection):
        self.connection = connection

    def _fetch(self, query: str, args=None) -> list:
        with self.connection.cursor() as cursor:
            cursor.execute(query, args)
            return cursor.fetchall()

    def try_lock(self) -> bool:
        # Transaction-scoped: released by the commit or rollback that ends the run.
        rows = self._fetch("SELECT pg_try_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
        return rows[0][0]

    def now(self) -> datetime:
        return self._fetch("SELECT now()")[0][0]

    def get_log_watermark(self) -> Optional[datetime]:
        rows = self._fetch("SELECT log_watermark FROM alerter_state WHERE singleton")
        return rows[0][0] if rows else None

    def fetch_log_rows(self, since: datetime) -> List[LogRow]:
        # ::timestamptz makes the result timezone-aware whether server_time is stored with
        # or without a zone; a zoneless value is read in the session time zone.
        rows = self._fetch(
            "SELECT server_time::timestamptz, server_type, server_id, log_level::text, device, "
            "filename, function, line_no, message, traceback, subject_id "
            "FROM log_application "
            "WHERE server_time > %(since)s AND log_level IN ('error', 'critical') "
            "ORDER BY server_time",
            {"since": since},
        )
        return [LogRow(*row) for row in rows]

    def fetch_dead_services(
        self, stale_after: timedelta, max_age: timedelta
    ) -> List[DeadServiceRow]:
        rows = self._fetch(
            "SELECT service_id, server_id, pid, last_beat, release_version "
            "FROM service_heartbeat "
            "WHERE stopped_at IS NULL "
            "AND last_beat < now() - %(stale_after)s AND last_beat > now() - %(max_age)s",
            {"stale_after": stale_after, "max_age": max_age},
        )
        return [DeadServiceRow(*row) for row in rows]

    def fetch_subject_ids(self) -> List[str]:
        return [row[0] for row in self._fetch("SELECT subject_id FROM subject")]

    def load_history(self, fingerprints: Sequence[str]) -> Dict[str, AlertRecord]:
        if not fingerprints:
            return {}
        rows = self._fetch(
            f"SELECT {', '.join(_HISTORY_COLUMNS)} FROM alert_history WHERE fingerprint = ANY(%s)",
            (list(fingerprints),),
        )
        return {row[0]: AlertRecord(*row) for row in rows}

    def save_history(self, records: Sequence[AlertRecord]) -> None:
        columns = ", ".join(_HISTORY_COLUMNS)
        placeholders = ", ".join(f"%({column})s" for column in _HISTORY_COLUMNS)
        updates = ", ".join(
            f"{column} = EXCLUDED.{column}" for column in _HISTORY_COLUMNS[1:]
        )
        query = (
            f"INSERT INTO alert_history ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT (fingerprint) DO UPDATE SET {updates}"
        )
        with self.connection.cursor() as cursor:
            for record in records:
                cursor.execute(
                    query,
                    {column: getattr(record, column) for column in _HISTORY_COLUMNS},
                )

    def save_state(self, log_watermark: datetime, run_at: datetime) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO alerter_state (singleton, log_watermark, last_run_at) "
                "VALUES (true, %(watermark)s, %(run_at)s) "
                "ON CONFLICT (singleton) DO UPDATE "
                "SET log_watermark = EXCLUDED.log_watermark, last_run_at = EXCLUDED.last_run_at",
                {"watermark": log_watermark, "run_at": run_at},
            )

    def list_alerts(self, include_acknowledged: bool) -> List[AlertRecord]:
        where = "" if include_acknowledged else "WHERE NOT acknowledged "
        rows = self._fetch(
            f"SELECT {', '.join(_HISTORY_COLUMNS)} FROM alert_history {where}ORDER BY last_seen DESC"
        )
        return [AlertRecord(*row) for row in rows]

    def acknowledge(self, fingerprint_prefix: str, acknowledged_by: str) -> str:
        """Acknowledge the one alert whose fingerprint starts with ``fingerprint_prefix``.

        Returns:
            The full fingerprint.

        Raises:
            ValueError: If the prefix matches no alert or more than one.
        """
        matches = self._fetch(
            "SELECT fingerprint FROM alert_history WHERE fingerprint LIKE %s",
            (fingerprint_prefix.replace("%", "").replace("_", "") + "%",),
        )
        if len(matches) != 1:
            raise ValueError(
                f"{fingerprint_prefix!r} matches {len(matches)} alerts; give more characters."
            )
        fingerprint = matches[0][0]
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE alert_history SET acknowledged = true, acknowledged_at = now(), "
                "acknowledged_by = %s WHERE fingerprint = %s",
                (acknowledged_by, fingerprint),
            )
        return fingerprint


# --- Run ------------------------------------------------------------------------------


def run_once(store: AlertStore, sender: Sender, settings: AlertingSpec) -> List[Alert]:
    """Read new failures, update the alert history and send one notification if needed.

    The caller commits only after this returns, so a failed send leaves the history and
    watermark unchanged and the next run tries again.

    Args:
        store: Database access.
        sender: Where notifications go.
        settings: Thresholds and labels.

    Returns:
        The alerts that were sent; empty if another alerter holds the lock.
    """
    if not store.try_lock():
        LOGGER.info("Another alerter is running against this database; skipping.")
        return []
    now = store.now()
    watermark = store.get_log_watermark() or now - timedelta(
        hours=settings.first_run_lookback_hours
    )
    # Re-read an overlap window: a booth whose clock runs slow, or a row committed late,
    # can land behind the watermark. merge_occurrences skips rows already counted.
    log_rows = store.fetch_log_rows(
        since=watermark - timedelta(minutes=settings.log_overlap_min)
    )
    dead_services = store.fetch_dead_services(
        stale_after=timedelta(seconds=settings.heartbeat_stale_sec),
        max_age=timedelta(hours=settings.dead_service_max_age_hours),
    )

    scrubber = Scrubber(store.fetch_subject_ids())
    occurrences = [occurrence_from_log_row(row, scrubber) for row in log_rows]
    occurrences += [occurrence_from_dead_service(row) for row in dead_services]

    history = store.load_history(sorted({o.fingerprint for o in occurrences}))
    changed, alerts = merge_occurrences(history, occurrences, now)
    store.save_history(changed)

    # Never move the watermark past now: one booth with a fast clock would hide others' rows.
    latest_row = max((row.server_time for row in log_rows), default=watermark)
    store.save_state(min(max(watermark, latest_row), now), now)

    if alerts:
        sender.send(*format_notification(alerts, settings.label))
    LOGGER.info(
        "Read %d log rows and %d dead services; %d fingerprints changed, %d alerted.",
        len(log_rows),
        len(dead_services),
        len(changed),
        len(alerts),
    )
    return alerts


def connect(settings: AlertingSpec):
    """Open the environment's database connection, in the configured time zone."""
    connection = metadator.get_database_connection(connect_timeout=10)
    with connection.cursor() as cursor:
        cursor.execute("SET TIME ZONE %s", (settings.timezone,))
    return connection


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="Check for new failures and notify")
    list_parser = commands.add_parser("list", help="Show unacknowledged alerts")
    list_parser.add_argument(
        "--all", action="store_true", help="Include acknowledged alerts"
    )
    ack_parser = commands.add_parser("ack", help="Acknowledge an alert")
    ack_parser.add_argument(
        "fingerprint", help="Fingerprint, or a unique prefix of one"
    )
    ack_parser.add_argument("--by", required=True, help="Who is acknowledging it")
    commands.add_parser("test-notify", help="Send a test notification to every channel")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg.load_config(validate_paths=False)
    settings = cfg.neurobooth_config.alerting
    if settings is None:
        raise cfg.ConfigException(
            "The neurobooth config has no 'alerting' section; see docs/booth_alerting.md."
        )

    try:
        if args.command == "test-notify":
            make_sender(settings).send(
                f"[{settings.label}] Booth alerter test",
                "This is a test notification from neurobooth_os.alerting.",
            )
        else:
            _run_database_command(args, settings)
    except Exception:
        # Scheduled runs have no console, so log_application is where this gets seen,
        # and the next successful run alerts on it like any other error.
        log_manager.make_db_logger(log_level=logging.WARNING).exception(
            "Booth alerter '%s' failed.", args.command
        )
        raise
    return 0


def _run_database_command(args: argparse.Namespace, settings: AlertingSpec) -> None:
    connection = connect(settings)
    try:
        store = PostgresAlertStore(connection)
        if args.command == "run":
            run_once(store, make_sender(settings), settings)
        elif args.command == "list":
            for record in store.list_alerts(include_acknowledged=args.all):
                state = "acked" if record.acknowledged else "OPEN "
                print(
                    f"{record.fingerprint} {state} {record.count:>6} "
                    f"{record.last_seen.isoformat(timespec='seconds')} "
                    f"{record.server_type:<6} {record.server_id} {record.location}  "
                    f"{record.normalized_message[:80]}"
                )
        elif args.command == "ack":
            print(f"Acknowledged {store.acknowledge(args.fingerprint, args.by)}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
