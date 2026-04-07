"""Tests for the XDF split backlog (postpone / postprocess roundtrip).

The backlog file embeds a JSON video_files dict inside a CSV line.
These tests verify that the serialization survives roundtripping,
including edge cases like empty dicts and values with special characters.
"""

import json
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
    def test_with_video_files(self, backlog_file):
        video_files = {"FLIR": ["task_flir.avi"], "IPhone": ["task_IPhone.mov", "task_IPhone.json"]}
        postpone_xdf_split("/data/test.xdf", "task_1", "log_1", backlog_file, video_files=video_files)

        line = _read_backlog(backlog_file).strip()
        parts = line.split(",", 3)  # Split into 4 parts: xdf, task, log, json
        assert parts[0] == "/data/test.xdf"
        assert parts[1] == "task_1"
        assert parts[2] == "log_1"
        assert json.loads(parts[3]) == video_files

    def test_without_video_files(self, backlog_file):
        postpone_xdf_split("/data/test.xdf", "task_1", "log_1", backlog_file)

        line = _read_backlog(backlog_file).strip()
        parts = line.split(",", 3)
        assert json.loads(parts[3]) == {}

    def test_multiple_entries(self, backlog_file):
        postpone_xdf_split("/data/a.xdf", "t1", "l1", backlog_file, video_files={"A": ["a.avi"]})
        postpone_xdf_split("/data/b.xdf", "t2", "l2", backlog_file, video_files={"B": ["b.bag"]})

        lines = _read_backlog(backlog_file).strip().split("\n")
        assert len(lines) == 2


class TestPostprocessRoundtrip:
    """Verify that what postpone writes, postprocess reads back correctly."""

    def test_roundtrip_passes_video_files_to_split(self, backlog_file):
        video_files = {"FLIR": ["task_flir.avi"], "Intel_1": ["task_intel1.bag"]}
        postpone_xdf_split("/data/test.xdf", "pursuit", "log_42", backlog_file, video_files=video_files)

        captured_calls = []

        def fake_split(xdf_path, log_task_id, task_id, conn, video_files=None):
            captured_calls.append({
                "xdf_path": xdf_path,
                "log_task_id": log_task_id,
                "task_id": task_id,
                "video_files": video_files,
            })

        with patch("neurobooth_os.iout.split_xdf.split_sens_files", side_effect=fake_split):
            postprocess_xdf_split(backlog_file, conn=MagicMock())

        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["xdf_path"] == "/data/test.xdf"
        assert call["task_id"] == "pursuit"
        assert call["log_task_id"] == "log_42"
        assert call["video_files"] == video_files

    def test_backlog_cleared_after_success(self, backlog_file):
        postpone_xdf_split("/data/test.xdf", "t1", "l1", backlog_file, video_files={"A": ["a.avi"]})

        with patch("neurobooth_os.iout.split_xdf.split_sens_files"):
            postprocess_xdf_split(backlog_file, conn=MagicMock())

        assert _read_backlog(backlog_file).strip() == ""

    def test_failed_entry_retained_in_backlog(self, backlog_file):
        postpone_xdf_split("/data/good.xdf", "t1", "l1", backlog_file, video_files={"A": ["a.avi"]})
        postpone_xdf_split("/data/bad.xdf", "t2", "l2", backlog_file, video_files={"B": ["b.bag"]})

        def fail_on_bad(xdf_path, log_task_id, task_id, conn, video_files=None):
            if "bad" in xdf_path:
                raise RuntimeError("simulated failure")

        with patch("neurobooth_os.iout.split_xdf.split_sens_files", side_effect=fail_on_bad):
            postprocess_xdf_split(backlog_file, conn=MagicMock())

        remaining = _read_backlog(backlog_file).strip()
        assert "bad.xdf" in remaining
        assert "good.xdf" not in remaining
