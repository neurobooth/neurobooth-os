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


# ---- Merrimac v0.92.8 staging dump (regression fixture) ---------------------
#
# Captured verbatim from the WARNING-level stdout dump emitted on
# subscription-handshake timeout, Merrimac staging, 2026-06-02. The
# 60s timeout failed for the bottom three names (IntelFrameIndex_cam1,
# IPhoneFrameIndex, mbient_LF); raising to 180s changed nothing because
# all 11 streams in fact subscribed within seconds and the deficit was
# purely a parser miss on the chewed-up confirmation lines. See the
# module-level comment in session_controller for the four interleaving
# shapes (a)-(d) and how the per-name regex handles each.

_MERRIMAC_V928_EXPECTED = [
    "EyeLink",
    "IntelFrameIndex_cam1",
    "IntelFrameIndex_cam2",
    "IntelFrameIndex_cam3",
    "FlirFrameIndex",
    "IPhoneFrameIndex",
    "mbient_LF",
    "Audio",
    "mbient_RF",
    "Marker",
    "Mouse",
]

# Lines 5-44 of the dump in chronological order (the user posted them
# newest-first; we feed oldest-first the way they actually arrived).
_MERRIMAC_V928_STDOUT = [
    "Found IntelFrameIndex_cam3@acq-staging matching 'source_id='5dc02fcd-180e-454e-8571-17f69cd5a7b7''",
    "Found FlirFrameIndex@acq-staging matching 'source_id='869dd14c-95c5-49b3-a173-50303862938c''",
    "Found IPhoneFrameIndex@acq-staging matching 'source_id='ba237963-b240-4492-9136-a1c372f04369''",
    "Found mbient_LF@stm-staging matching 'source_id='7a43cef9-090c-4bfa-816c-213bca7cf3c6''",
    "Found Audio@acq-staging matching 'source_id='f677385d-aaaa-4d63-9173-5e53ddd9fc70''",
    "Found mbient_RF@stm-staging matching 'source_id='667353f9-b465-4c03-adb2-50661988f68c''",
    "Starting the recording, press Enter to quit",
    "Opened the stream EyeLink.",
    "Opened the stream IntelFrameIndex_cam2.",
    "Opened the stream IntelFrameIndex_cam3.",
    "Opened the stream FlirFrameIndex.",
    "Opened the stream IPhoneFrameIndex.",
    "Opened the stream mbient_LF.",
    "Received header for stream IntelFrameIndex_cam2.",
    "Opened the stream Audio.",
    "Received header for stream IntelFrameIndex_cam3.",
    "Opened the stream mbient_RF.",
    "Received header for stream FlirFrameIndex.",
    "Received header for stream IPhoneFrameIndex.",
    "Received header for stream mbient_LF.",
    "Received header for stream EyeLink.",
    "Received header for stream Audio.",
    "Received header for stream mbient_RF.",
    "Opened the stream Marker.",
    "Opened the stream Mouse.",
    "Opened the stream IntelFrameIndex_cam1.",
    "Received header for stream Marker.",
    "Received header for stream Mouse.",
    "Received header for stream IntelFrameIndex_cam1.",
    # Confirmation phase begins -- this is where the interleaving lives.
    # (a) two concatenated, both with prefix; (d) tail name "IntelFrameIndex_cam1" with no trailing period:
    "Started data collection for stream Audio.Started data collection for stream mbient_RF.Started data collection for stream Started data collection for stream FlirFrameIndex.Started data collection for stream IntelFrameIndex_cam3.Started data collection for stream IntelFrameIndex_cam1",
    "Started data collection for stream Started data collection for stream Mouse..",
    "",
    "",
    # (c) prefix on this line, name on the next; (a) also shows another concatenation start at line end:
    "EyeLink.Started data collection for stream",
    "IPhoneFrameIndex.",
    "",
    "Started data collection for stream Marker.",
    "",
    "mbient_LF.",
    "Started data collection for stream IntelFrameIndex_cam2.",
]


def test_handshake_handles_merrimac_v928_dump(proc, logger):
    """Regression: feed the exact LabRecorderCLI stdout that triggered
    the 'three streams failed at 180s' false-timeout on Merrimac, and
    assert the parser now recognizes all 11 subscriptions.

    Before the v0.92.9 parser change this test fails with confirmed=8,
    missing={IntelFrameIndex_cam1, IPhoneFrameIndex, mbient_LF} -- the
    three streams whose confirmation message either lost its trailing
    period (cam1) or landed on a line without the prefix (the other
    two).
    """

    def feed():
        time.sleep(0.05)
        for line in _MERRIMAC_V928_STDOUT:
            proc.write_line(line)

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, _MERRIMAC_V928_EXPECTED, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == set(_MERRIMAC_V928_EXPECTED)


# ---- Merrimac v0.92.9 staging dump (shape (e) regression fixture) -----------
#
# Second-round failure captured 2026-06-03 after v0.92.9 deploy. The
# parser now confirms 10 of 11 streams; mbient_LF still misses because
# its confirmation message arrived as THREE separate lines:
#
#     line 36: ...Started data collection for stream mbient_RF.Started data collection for stream
#     line 37: mbient_LF
#     line 38: .
#
# i.e. the literal space between "stream" and "mbient_LF" was replaced
# by a newline (interleaving from another thread), and the trailing
# period landed on its own line below. The v0.92.9 patterns required
# either a single space between prefix and name (Pattern A) or the
# period immediately adjacent to the name (Pattern B). The v0.92.10
# patch widens Pattern A's separator to ``\s+`` and Pattern B's trail
# to ``.|\n.``, covering this new shape (e) while staying tight enough
# to not false-confirm on "Opened/Received/Subscribing" lines.

_MERRIMAC_V929_EXPECTED = [
    "IntelFrameIndex_cam1",
    "Mouse",
    "IntelFrameIndex_cam2",
    "mbient_RF",
    "mbient_LF",
    "EyeLink",
    "Marker",
    "Audio",
    "IPhoneFrameIndex",
    "IntelFrameIndex_cam3",
    "FlirFrameIndex",
]

_MERRIMAC_V929_STDOUT = [
    "Found mbient_LF@stm-staging matching 'source_id='96648ed0-ec60-4865-a4d7-4fe957225cc7''",
    "Found FlirFrameIndex@acq-staging matching 'source_id='069a82f3-c2be-46db-8267-e5ff7b47f4e9''",
    "Found IPhoneFrameIndex@acq-staging matching 'source_id='1ee2e267-2be4-4218-9426-ab90a2127f38''",
    "Found mbient_RF@stm-staging matching 'source_id='7c1b424f-b5fe-49e7-acdf-70aeb2693dfb''",
    "Found Audio@acq-staging matching 'source_id='c80c2841-37e0-4308-9ab2-c9872b075921''",
    "Starting the recording, press Enter to quit",
    "Opened the stream EyeLink.Opened the stream Marker.",
    "",
    "Opened the stream Mouse.",
    "Opened the stream IntelFrameIndex_cam1.",
    "Opened the stream IntelFrameIndex_cam2.",
    "Received header for stream Marker.",
    "Opened the stream IntelFrameIndex_cam3.",
    "Received header for stream Mouse.",
    "Opened the stream mbient_LF.",
    "Opened the stream FlirFrameIndex.",
    "Received header for stream IntelFrameIndex_cam1.",
    "Opened the stream IPhoneFrameIndex.",
    "Opened the stream mbient_RF.",
    "Received header for stream IntelFrameIndex_cam2.",
    "Received header for stream IntelFrameIndex_cam3.",
    "Received header for stream FlirFrameIndex.",
    "Received header for stream EyeLink.",
    "Received header for stream mbient_LF.",
    "Opened the stream Audio.",
    "Received header for stream IPhoneFrameIndex.",
    "Received header for stream mbient_RF.",
    "Received header for stream Audio.",
    # Confirmation phase begins. Lines 34-44 contain shape (a), (e),
    # and (c) interleavings:
    "Started data collection for stream IntelFrameIndex_cam1.Started data collection for stream Mouse.Started data collection for stream IntelFrameIndex_cam2.Started data collection for stream",
    "",
    # Shape (e) splits the next mbient_LF confirmation across three lines:
    "Started data collection for stream mbient_RF.Started data collection for stream",
    "mbient_LF",
    ".",
    "Started data collection for stream EyeLink.",
    "Started data collection for stream Marker.",
    # Shape (c): bare "Audio." on its own line, lost its prefix entirely:
    "Audio.",
    "Started data collection for stream IPhoneFrameIndex.",
    "Started data collection for stream IntelFrameIndex_cam3.",
    "Started data collection for stream FlirFrameIndex.",
]


def test_handshake_handles_merrimac_v929_dump(proc, logger):
    """Regression: feed the exact v0.92.9 Merrimac stdout that left
    mbient_LF unconfirmed at 60s, and assert the v0.92.10 parser now
    recognizes all 11 subscriptions.

    Before the v0.92.10 patch this test fails with confirmed=10,
    missing={'mbient_LF'} -- the confirmation arrived split across
    three lines (prefix / name / period) because two newlines from
    other writer threads landed inside LRCLI's printf for that one
    message.
    """

    def feed():
        time.sleep(0.05)
        for line in _MERRIMAC_V929_STDOUT:
            proc.write_line(line)

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, _MERRIMAC_V929_EXPECTED, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == set(_MERRIMAC_V929_EXPECTED)


def test_handshake_handles_three_line_split(proc, logger):
    """Minimal isolation of shape (e): the confirmation for a single
    stream arrives as prefix / name / period on three consecutive
    lines, with nothing else in between. The parser must still confirm.
    """
    expected = ["mbient_LF"]

    def feed():
        time.sleep(0.05)
        # Note write_line appends a "\n", so the three writes here
        # produce: "Started data collection for stream\nmbient_LF\n.\n"
        proc.write_line("Started data collection for stream")
        proc.write_line("mbient_LF")
        proc.write_line(".")

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == {"mbient_LF"}


# ---- Merrimac v0.92.10 staging dump (shape (f) regression fixture) ----------
#
# Third-round failure captured 2026-06-03 after v0.92.10 deploy. The
# parser now confirms 12 of 14 streams via per-name regex; Mouse and
# mbient_LF still miss because their confirmation messages landed as
#
#     line 47: Mousembient_LF.Started data collection for stream
#
# i.e. two names were jammed together with NO separator -- no period,
# no whitespace, no newline between them. No regex over the buffer can
# split "Mousembient_LF" into "Mouse" and "mbient_LF" without either
# positional anchoring (which the interleaving destroys) or naive
# substring containment (which false-matches "Found X@..." chatter).
#
# v0.92.11 retires per-name strict matching as the success gate and
# uses the marker count instead. Each "Started data collection for
# stream" substring corresponds to exactly one completed subscription
# printf call; the count is interleaving-immune. This dump has 14
# marker occurrences for 14 expected streams, so count-based success
# fires regardless of how Mouse and mbient_LF interleaved.
#
# Note also: this booth has five Mbients now (LF, RF, LH, RH, BK), up
# from two in the v0.92.9 dump -- which increased interleaving
# pressure on LRCLI's stdout and surfaced shape (f).

_MERRIMAC_V9210_EXPECTED = [
    "Audio",
    "EyeLink",
    "FlirFrameIndex",
    "IntelFrameIndex_cam1",
    "IntelFrameIndex_cam2",
    "IntelFrameIndex_cam3",
    "IPhoneFrameIndex",
    "mbient_BK",
    "mbient_LF",
    "mbient_LH",
    "mbient_RF",
    "mbient_RH",
    "Marker",
    "Mouse",
]

_MERRIMAC_V9210_STDOUT = [
    "Opened the stream IntelFrameIndex_cam1.",
    "Opened the stream Marker.",
    "Opened the stream IntelFrameIndex_cam2.",
    "Opened the stream IntelFrameIndex_cam3.",
    "Opened the stream FlirFrameIndex.",
    "Received header for stream IntelFrameIndex_cam1.",
    "Received header for stream Marker.",
    "Received header for stream IntelFrameIndex_cam2.",
    "Opened the stream IPhoneFrameIndex.",
    "Received header for stream FlirFrameIndex.",
    "Received header for stream IntelFrameIndex_cam3.",
    "Opened the stream mbient_RF.",
    "Opened the stream mbient_LF.",
    "Received header for stream mbient_RF.",
    "Received header for stream mbient_LF.",
    "Opened the stream Mouse.",
    "Opened the stream EyeLink.",
    "Received header for stream Mouse.",
    "Received header for stream IPhoneFrameIndex.",
    "Opened the stream mbient_BK.",
    "Opened the stream mbient_RH.",
    "Received header for stream mbient_BK.",
    "Opened the stream mbient_LH.",
    "Received header for stream EyeLink.",
    "Received header for stream mbient_RH.",
    "Received header for stream mbient_LH.",
    "Opened the stream Audio.",
    "Received header for stream Audio.",
    # Confirmation phase. Lines 43-56 contain shapes (a), (b), and (f):
    "Started data collection for stream mbient_RH.Started data collection for stream FlirFrameIndex.",
    "Started data collection for stream IntelFrameIndex_cam2.Started data collection for stream mbient_LH",
    ".Started data collection for stream Started data collection for stream IntelFrameIndex_cam3.Started data collection for stream mbient_BK",
    "Started data collection for stream Started data collection for stream .mbient_RF.",
    # Shape (f): Mouse and mbient_LF concatenated with no separator:
    "Mousembient_LF.Started data collection for stream",
    "",
    ".",
    "",
    "Started data collection for stream EyeLink.",
    "Started data collection for stream Audio.",
    "",
    "IPhoneFrameIndex.",
    "Started data collection for stream Marker.",
    "Started data collection for stream IntelFrameIndex_cam1.",
]


def test_handshake_handles_merrimac_v9210_dump(proc, logger):
    """Regression: feed the v0.92.10 Merrimac stdout that left Mouse
    and mbient_LF unconfirmed at 60s, and assert the v0.92.11 count
    gate now declares all 14 streams confirmed.

    Before v0.92.11 this test fails with confirmed=12, missing={Mouse,
    mbient_LF}. After v0.92.11 the marker_count substring counter
    reaches 14 (matching the expected count) without needing to
    disambiguate ``Mousembient_LF`` into its constituent names.
    """

    def feed():
        time.sleep(0.05)
        for line in _MERRIMAC_V9210_STDOUT:
            proc.write_line(line)

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, _MERRIMAC_V9210_EXPECTED, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == set(_MERRIMAC_V9210_EXPECTED)


def test_handshake_counts_empty_prefix_markers(proc, logger):
    """Minimal isolation of shape (f)'s count semantics: emit N marker
    substrings with mangled/missing names, including some "empty
    prefix" markers (two ``Started data collection for stream``s
    back-to-back with no name between them). Each marker corresponds
    to one printf call from one subscription thread, so the count gate
    must accept regardless of whether the names are parseable.
    """
    expected = ["Stream_A", "Stream_B", "Stream_C"]

    def feed():
        time.sleep(0.05)
        # Three markers, but names are pathologically interleaved.
        # buffer.count(_LRCLI_STARTED_MARKER) should still hit 3.
        proc.write_line("Started data collection for stream Started data collection for stream Stream_AStream_B.")
        proc.write_line("Started data collection for stream Stream_C.")

    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    assert confirmed == set(expected)


def test_handshake_does_not_confirm_on_opened_stream_lines(proc, logger):
    """Pattern 2 of the v0.92.9 parser (bare ``NAME.`` preceded by
    newline or period) must not false-match on ``Opened the stream
    NAME.`` or ``Received header for stream NAME.`` lines, where NAME is
    preceded by a space, not a newline or period.

    Otherwise a stream would be confirmed *before* LRCLI actually
    started recording its samples, defeating the purpose of the
    handshake.
    """
    expected = ["EyeLink"]

    def feed():
        time.sleep(0.05)
        # All of these have EyeLink preceded by a space (after "stream "),
        # which must NOT count as a confirmation. Only the final
        # "Started data collection" line should trip the handshake.
        proc.write_line("Found EyeLink@stm matching 'source_id=abc'.")
        proc.write_line("Opened the stream EyeLink.")
        proc.write_line("Received header for stream EyeLink.")
        # Sleep before the real confirmation so a buggy parser would
        # have time to confirm early and we'd see the wrong elapsed.
        time.sleep(0.2)
        proc.write_line("Started data collection for stream EyeLink.")

    t0 = time.time()
    threading.Thread(target=feed, daemon=True).start()
    confirmed = wait_for_lrcli_subscriptions(
        proc, expected, timeout_seconds=5.0, logger=logger
    )
    elapsed = time.time() - t0
    assert confirmed == {"EyeLink"}
    # The real confirmation arrives ~0.25s in; if the parser falsely
    # confirmed on the "Opened" line at ~0.05s we'd return well under
    # 0.2s. Give a generous margin.
    assert elapsed >= 0.2
