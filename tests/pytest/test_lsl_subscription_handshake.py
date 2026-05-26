"""Tests for the LabRecorderCLI subscription handshake in
``neurobooth_os.session_controller.wait_for_lrcli_subscriptions``.

Background: LabRecorderCLI's per-stream subscription is async and can
take many seconds on slow cross-host paths (#812 / #814). The previous
``start_lsl_recording`` returned the moment the subprocess spawned,
leaving short tasks (progress_bar, coord_pause) to race a stop signal
against still-in-progress subscriptions. The handshake closes that
race by waiting until LabRecorderCLI prints
``Started data collection for stream <name>`` for every expected stream.

These tests mock the subprocess via an ``os.pipe()``-backed object so
the blocking semantics of the real subprocess's stdout (no ``select``
on Windows, ``readline`` blocks until newline or EOF) are exercised
faithfully -- no timing assumptions on top of synthetic-stream
fixtures.
"""
from __future__ import annotations

import io
import logging
import os
import threading
import time
from typing import List, Optional

import pytest

from neurobooth_os.session_controller import (
    SubscriptionHandshakeTimeout,
    wait_for_lrcli_subscriptions,
)


class _FakeProcess:
    """Minimal subprocess.Popen stand-in driven by an os.pipe().

    ``write_line`` (called from the test thread) writes one line into
    the pipe; ``stdout.readline`` (called from the handshake's reader
    thread) blocks until that line arrives, mirroring real
    LabRecorderCLI behaviour on Windows where you can't poll PIPE
    handles without a thread.
    """

    def __init__(self) -> None:
        self._read_fd, self._write_fd = os.pipe()
        # Wrap the read end in a buffered binary file so readline() works
        # the same as on subprocess.Popen.stdout (BufferedReader).
        self.stdout = os.fdopen(self._read_fd, "rb", buffering=0)
        self._exited_with: Optional[int] = None

    def write_line(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        os.write(self._write_fd, line.encode("utf-8"))

    def write_raw(self, data: bytes) -> None:
        os.write(self._write_fd, data)

    def close_stdout(self) -> None:
        os.close(self._write_fd)

    def exit(self, code: int = 0) -> None:
        self._exited_with = code
        try:
            os.close(self._write_fd)
        except OSError:
            pass

    def poll(self) -> Optional[int]:
        return self._exited_with


@pytest.fixture
def proc():
    p = _FakeProcess()
    yield p
    try:
        p.exit(0)
    except OSError:
        pass


@pytest.fixture
def logger():
    log = logging.getLogger("test.lsl_handshake")
    log.setLevel(logging.DEBUG)
    return log


# ---- happy paths ------------------------------------------------------------


def test_handshake_returns_when_all_streams_confirm(proc, logger):
    expected = ["EyeLink", "Marker", "Mouse"]

    def feed():
        time.sleep(0.05)
        proc.write_line("Opened the stream EyeLink.")
        proc.write_line("Started data collection for stream EyeLink.")
        proc.write_line("Started data collection for stream Marker.")
        proc.write_line("Started data collection for stream Mouse.")

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == set(expected)


def test_handshake_ignores_non_matching_lines(proc, logger):
    """Unrelated stdout chatter (Found... / Opened... / Subscribing...)
    must not be misread as subscription confirmations."""
    expected = ["FlirFrameIndex"]

    def feed():
        time.sleep(0.05)
        proc.write_line("Found FlirFrameIndex@acq matching 'source_id=abc'.")
        proc.write_line("Opened the stream FlirFrameIndex.")
        proc.write_line("Received header for stream FlirFrameIndex.")
        proc.write_line(
            "Subscribing to the stream FlirFrameIndex is taking relatively long; "
            "collection from this stream will be delayed."
        )
        proc.write_line("Started data collection for stream FlirFrameIndex.")

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == {"FlirFrameIndex"}


def test_handshake_handles_interleaved_garbled_output(proc, logger):
    """Production traces show LabRecorderCLI worker threads writing
    stdout concurrently without locking, producing lines like:

        Started data collection for stream Started data collection
        for stream mbient_LH.IntelFrameIndex_cam2.

    The handshake must still extract every name via findall, not
    line-by-line match."""
    expected = ["mbient_LH", "IntelFrameIndex_cam2", "IPhoneFrameIndex"]

    def feed():
        time.sleep(0.05)
        proc.write_raw(
            b"Started data collection for stream Started data collection "
            b"for stream mbient_LH.IntelFrameIndex_cam2.\r\n"
        )
        proc.write_line("Started data collection for stream IPhoneFrameIndex.")

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == set(expected)


def test_handshake_empty_expected_returns_immediately(proc, logger):
    """If we somehow ended up with no expected streams (degenerate
    config), the handshake should return cleanly without reading
    anything from the subprocess."""
    t0 = time.time()
    confirmed = wait_for_lrcli_subscriptions(
        proc, [], timeout_seconds=5.0, logger=logger
    )
    assert confirmed == set()
    assert (time.time() - t0) < 0.2  # should be near-instant


# ---- timeout paths ----------------------------------------------------------


def test_handshake_times_out_when_streams_missing(proc, logger):
    expected = ["EyeLink", "Marker", "Mouse", "mbient_RF"]

    def feed():
        time.sleep(0.05)
        # Confirm only 2 of 4
        proc.write_line("Started data collection for stream EyeLink.")
        proc.write_line("Started data collection for stream Marker.")
        # Never confirm Mouse or mbient_RF

    threading.Thread(target=feed, daemon=True).start()
    with pytest.raises(SubscriptionHandshakeTimeout) as exc:
        wait_for_lrcli_subscriptions(
            proc, expected, timeout_seconds=0.5, logger=logger
        )
    assert exc.value.confirmed == {"EyeLink", "Marker"}
    assert exc.value.missing == {"Mouse", "mbient_RF"}
    assert exc.value.elapsed_seconds >= 0.5


def test_handshake_timeout_reports_zero_confirmed(proc, logger):
    """Worst case: nothing comes through stdout at all."""
    expected = ["EyeLink"]
    with pytest.raises(SubscriptionHandshakeTimeout) as exc:
        wait_for_lrcli_subscriptions(
            proc, expected, timeout_seconds=0.3, logger=logger
        )
    assert exc.value.confirmed == set()
    assert exc.value.missing == {"EyeLink"}


# ---- premature exit ---------------------------------------------------------


def test_handshake_raises_if_subprocess_exits_prematurely(proc, logger):
    """LabRecorderCLI segfaulting (or 'matched no stream'-exiting)
    before all subscriptions confirm is unrecoverable; we should raise
    a clear error rather than silently waiting for the timeout."""
    expected = ["EyeLink", "Marker"]

    def feed_then_die():
        time.sleep(0.05)
        proc.write_line("Started data collection for stream EyeLink.")
        # Don't confirm Marker; simulate a crash
        time.sleep(0.05)
        proc.exit(3221225477)  # 0xC0000005 STATUS_ACCESS_VIOLATION

    threading.Thread(target=feed_then_die, daemon=True).start()
    with pytest.raises(RuntimeError, match="exited prematurely"):
        wait_for_lrcli_subscriptions(
            proc, expected, timeout_seconds=5.0, logger=logger
        )


# ---- duplicate / extra confirmations ---------------------------------------


def test_handshake_tolerates_repeat_confirmations(proc, logger):
    """If a stream's confirmation line appears twice (which we haven't
    observed but is harmless to handle), the handshake must not
    double-count or hang."""
    expected = ["EyeLink", "Marker"]

    def feed():
        time.sleep(0.05)
        proc.write_line("Started data collection for stream EyeLink.")
        proc.write_line("Started data collection for stream EyeLink.")
        proc.write_line("Started data collection for stream Marker.")

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == {"EyeLink", "Marker"}


def test_handshake_ignores_unexpected_stream_names(proc, logger):
    """Lines for streams we didn't ask about must not satisfy or
    confuse the handshake."""
    expected = ["EyeLink"]

    def feed():
        time.sleep(0.05)
        proc.write_line("Started data collection for stream UnknownStream.")
        proc.write_line("Started data collection for stream AnotherUnknown.")
        proc.write_line("Started data collection for stream EyeLink.")

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == {"EyeLink"}
