"""Tests for the platform-neutral data move in :mod:`neurobooth_os.transfer_data`.

The booths move session data with ``robocopy /MOVE``, which does not exist off
Windows. These cover the standard-library replacement and the dispatch between
the two, on any platform.
"""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neurobooth_os import transfer_data


@pytest.fixture(autouse=True)
def module_logger():
    """transfer_data binds its logger at __main__ time, so supply one."""
    transfer_data.logger = logging.getLogger("test-transfer")
    yield


@pytest.fixture
def tree(tmp_path):
    """A small source tree with nesting and an already-empty directory."""
    source = tmp_path / "local"
    (source / "sub" / "deeper").mkdir(parents=True)
    (source / "top.txt").write_text("top")
    (source / "sub" / "middle.txt").write_text("middle")
    (source / "sub" / "deeper" / "leaf.txt").write_text("leaf")
    return source, tmp_path / "remote"


class TestMoveTreeShutil:
    def test_moves_every_file_preserving_structure(self, tree):
        source, destination = tree
        transfer_data._move_tree_shutil(str(source), str(destination))

        assert (destination / "top.txt").read_text() == "top"
        assert (destination / "sub" / "middle.txt").read_text() == "middle"
        assert (destination / "sub" / "deeper" / "leaf.txt").read_text() == "leaf"

    def test_source_files_are_gone_afterwards(self, tree):
        """/MOVE means move, not copy. Leaving originals would fill the booth."""
        source, destination = tree
        transfer_data._move_tree_shutil(str(source), str(destination))

        remaining = [p for p in source.rglob("*") if p.is_file()]
        assert remaining == []

    def test_emptied_subdirectories_are_removed(self, tree):
        source, destination = tree
        transfer_data._move_tree_shutil(str(source), str(destination))

        assert not (source / "sub").exists()

    def test_source_root_survives(self, tree):
        """main() recreates the root afterwards, but removing it mid-move
        would break a concurrent writer holding the path open."""
        source, destination = tree
        transfer_data._move_tree_shutil(str(source), str(destination))
        assert source.exists()

    def test_creates_destination_when_absent(self, tree):
        source, destination = tree
        assert not destination.exists()
        transfer_data._move_tree_shutil(str(source), str(destination))
        assert destination.is_dir()

    def test_merges_into_existing_destination(self, tree):
        """shutil.move would nest source inside a destination that exists.

        robocopy /MOVE merges. This pins the merge behaviour, since getting it
        wrong produces remote/local/... instead of remote/... and the data is
        silently in the wrong place.
        """
        source, destination = tree
        destination.mkdir()
        (destination / "previous.txt").write_text("previous")

        transfer_data._move_tree_shutil(str(source), str(destination))

        assert (destination / "previous.txt").read_text() == "previous"
        assert (destination / "top.txt").exists()
        assert not (destination / "local").exists()

    def test_empty_source_is_not_an_error(self, tmp_path):
        source = tmp_path / "empty"
        source.mkdir()
        transfer_data._move_tree_shutil(str(source), str(tmp_path / "remote"))
        assert (tmp_path / "remote").is_dir()


class TestMoveTreeDispatch:
    def test_uses_robocopy_on_windows(self, monkeypatch):
        monkeypatch.setattr(transfer_data.sys, "platform", "win32")
        with patch.object(transfer_data, "_move_tree_robocopy") as robocopy:
            transfer_data.move_tree("a", "b")
        robocopy.assert_called_once_with("a", "b")

    @pytest.mark.parametrize("platform", ["darwin", "linux"])
    def test_uses_shutil_elsewhere(self, monkeypatch, platform):
        monkeypatch.setattr(transfer_data.sys, "platform", platform)
        with patch.object(transfer_data, "_move_tree_shutil") as shutil_move:
            transfer_data.move_tree("a", "b")
        shutil_move.assert_called_once_with("a", "b")


class TestRobocopyExitCodes:
    """robocopy exit codes are a bit field: <8 is success, >=8 is failure.

    Treating every non-zero code as failure would make a normal copy look
    broken; treating every code as success would hide a real one.
    """

    def _run(self, return_code):
        process = MagicMock()
        process.stdout.__enter__.return_value = iter([])
        process.stdout.readline.return_value = b""
        process.wait.return_value = return_code
        with patch.object(transfer_data, "Popen", return_value=process):
            transfer_data._move_tree_robocopy("a", "b")

    @pytest.mark.parametrize("code", [0, 1, 3, 7])
    def test_below_eight_succeeds(self, code):
        self._run(code)

    @pytest.mark.parametrize("code", [8, 16])
    def test_eight_and_above_raises(self, code):
        with pytest.raises(OSError, match="robocopy failed"):
            self._run(code)
