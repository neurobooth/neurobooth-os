"""Tests for the XDF split backlog (postpone / postprocess roundtrip).

The backlog records XDFs that need to be split during post-processing. Each
line has the format ``{xdf_path},{task_id},{log_task_id}``. Video filenames
are no longer threaded through the backlog — ACQ writes them to
log_sensor_file at device-start time.

These tests also exercise the backward-compat path: old entries with a
trailing JSON video_files blob should still be processed (extra columns
ignored).
"""

import pytest
from unittest.mock import patch, MagicMock

from neurobooth_os.iout.split_xdf import postpone_xdf_split, postprocess_xdf_split


@pytest.fixture
def backlog_file(tmp_path):
    return str(tmp_path / "backlog.csv")


def _read_backlog(path):
    with open(path) as f:
        return f.read()


class TestPostponeWritesCorrectFormat:
    def test_basic_entry(self, backlog_file):
        postpone_xdf_split("/data/test.xdf", "task_1", "log_1", backlog_file)

        line = _read_backlog(backlog_file).strip()
        assert line == "/data/test.xdf,task_1,log_1"

    def test_multiple_entries(self, backlog_file):
        postpone_xdf_split("/data/a.xdf", "t1", "l1", backlog_file)
        postpone_xdf_split("/data/b.xdf", "t2", "l2", backlog_file)

        lines = _read_backlog(backlog_file).strip().split("\n")
        assert len(lines) == 2


class TestPostprocessRoundtrip:
    """Verify that what postpone writes, postprocess reads back correctly."""

    def test_roundtrip_calls_split(self, backlog_file):
        postpone_xdf_split("/data/test.xdf", "pursuit", "log_42", backlog_file)

        captured_calls = []

        def fake_split(xdf_path, log_task_id, task_id, conn):
            captured_calls.append({
                "xdf_path": xdf_path,
                "log_task_id": log_task_id,
                "task_id": task_id,
            })

        with patch("neurobooth_os.iout.split_xdf.split_sens_files", side_effect=fake_split):
            postprocess_xdf_split(backlog_file, conn=MagicMock())

        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["xdf_path"] == "/data/test.xdf"
        assert call["task_id"] == "pursuit"
        assert call["log_task_id"] == "log_42"

    def test_backlog_cleared_after_success(self, backlog_file):
        postpone_xdf_split("/data/test.xdf", "t1", "l1", backlog_file)

        with patch("neurobooth_os.iout.split_xdf.split_sens_files"):
            postprocess_xdf_split(backlog_file, conn=MagicMock())

        assert _read_backlog(backlog_file).strip() == ""

    def test_failed_entry_retained_in_backlog(self, backlog_file):
        postpone_xdf_split("/data/good.xdf", "t1", "l1", backlog_file)
        postpone_xdf_split("/data/bad.xdf", "t2", "l2", backlog_file)

        def fail_on_bad(xdf_path, log_task_id, task_id, conn):
            if "bad" in xdf_path:
                raise RuntimeError("simulated failure")

        with patch("neurobooth_os.iout.split_xdf.split_sens_files", side_effect=fail_on_bad):
            postprocess_xdf_split(backlog_file, conn=MagicMock())

        remaining = _read_backlog(backlog_file).strip()
        assert "bad.xdf" in remaining
        assert "good.xdf" not in remaining


class TestOldBacklogFormatCompat:
    """Old backlog entries had a trailing JSON video_files blob. The new
    postprocess code accepts these by ignoring any columns after the third.
    """

    def test_old_format_entry_is_processed(self, backlog_file):
        with open(backlog_file, "w") as f:
            f.write('/data/old.xdf,task_old,log_old,{"FLIR": ["task_flir.avi"]}\n')

        captured_calls = []

        def fake_split(xdf_path, log_task_id, task_id, conn):
            captured_calls.append((xdf_path, task_id, log_task_id))

        with patch("neurobooth_os.iout.split_xdf.split_sens_files", side_effect=fake_split):
            postprocess_xdf_split(backlog_file, conn=MagicMock())

        assert captured_calls == [("/data/old.xdf", "task_old", "log_old")]
