"""Tests for LabRecorderCLI start at task start (#811).

Covers waiting for the previous recorder to exit and the retry failsafe when
LabRecorderCLI misses a stream.
"""

import logging
from typing import List

import pytest

import neurobooth_os.session_controller as sc
from neurobooth_os.session_controller import SessionController, SessionState

_LOGGER = "test_lsl_start_retry"


class _FakeSession:
    """Stand-in for liesl.Session that fails a set number of times."""

    def __init__(self, failures: int, error_sid: str = "sid-iphone") -> None:
        self.failures = failures
        self.error_sid = error_sid
        self.calls: List[str] = []

    def start_recording(self, task: str) -> None:
        self.calls.append(task)
        if len(self.calls) <= self.failures:
            # Shape of the real liesl error: LabRecorderCLI stdout as bytes, with
            # the streams it did find listed before the one it missed.
            raise ConnectionError(
                (
                    "Found Marker@host matching 'source_id='sid-marker''\r\n"
                    f"\"source_id='{self.error_sid}'\" matched no stream!\r\n"
                    "2026-10-01 18:10:23.218 netinterfaces.cpp:36 INFO| netif\r\n"
                ).encode()
            )


@pytest.fixture
def sleeps(monkeypatch) -> List[float]:
    recorded: List[float] = []
    monkeypatch.setattr(sc.time_mod, "sleep", recorded.append)
    return recorded


def _controller(session: _FakeSession) -> SessionController:
    state = SessionState()
    state.stream_ids = {
        "Marker": "sid-marker",
        "Audio": "sid-audio",
        "IPhoneFrameIndex": "sid-iphone",
    }
    state.session = session
    return SessionController(state, logging.getLogger(_LOGGER))


def test_first_attempt_success_does_not_retry(sleeps):
    session = _FakeSession(failures=0)
    _controller(session)._start_recording_with_retry("f")

    assert session.calls == ["f"]
    assert sleeps == []


def test_retries_until_recorder_finds_all_streams(sleeps):
    n_attempts = len(SessionController.LSL_START_RETRY_DELAYS_S) + 1
    session = _FakeSession(failures=n_attempts - 1)
    _controller(session)._start_recording_with_retry("f")

    assert session.calls == ["f"] * n_attempts
    assert sleeps == list(SessionController.LSL_START_RETRY_DELAYS_S)


def test_reraises_after_all_attempts_fail(sleeps):
    n_attempts = len(SessionController.LSL_START_RETRY_DELAYS_S) + 1
    session = _FakeSession(failures=n_attempts)

    with pytest.raises(ConnectionError):
        _controller(session)._start_recording_with_retry("f")
    assert len(session.calls) == n_attempts


def test_retry_budget_fits_inside_stm_wait():
    # STM waits ~30 s for LslRecording; the stop-thread join can take up to 10 s.
    assert sum(SessionController.LSL_START_RETRY_DELAYS_S) <= 5


def test_failure_log_names_only_the_missing_stream(sleeps, caplog):
    session = _FakeSession(failures=1, error_sid="sid-audio")

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        _controller(session)._start_recording_with_retry("f")
    assert "missed stream(s) ['Audio']" in caplog.text
    assert "started on attempt 2/" in caplog.text


def test_waits_for_previous_recorder_before_starting(monkeypatch):
    events: List[str] = []
    session = _FakeSession(failures=0)
    session.start_recording = lambda task: events.append("start")
    ctrl = _controller(session)
    monkeypatch.setattr(ctrl, "_join_lsl_stop", lambda: events.append("join"))
    monkeypatch.setattr(sc.meta, "post_message", lambda msg: None)

    ctrl.start_lsl_recording("subj", "task", "t_obs", "log_1", "12h-00m-00s")

    assert events == ["join", "start"]
