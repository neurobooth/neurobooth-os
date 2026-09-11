"""Tests for :mod:`neurobooth_os.util.file_lock`.

The cross-process contention test uses a **subprocess**, not a same-process
second acquire, for two reasons that differ by platform:

* Windows byte-range lock semantics for two handles in the same process are
  documented by Microsoft as undefined and differ across editions.
* POSIX ``lockf`` locks are owned per process, so a same-process re-acquire
  succeeds by design and would prove nothing.

The scenario the lock actually guards is always two separate processes racing
on a double-click, so the test exercises that directly. Do not simplify it.

This is the platform-neutral counterpart to ``test_gui_single_instance.py``,
which stays Windows-only because it covers the ``gui.py`` lock-file payload.
"""

import os
import subprocess
import sys
import textwrap

import pytest

from neurobooth_os.util import file_lock


@pytest.fixture
def lock_file(tmp_path):
    path = tmp_path / "gui.lock"
    path.write_bytes(b" ")
    return path


def _open(path):
    return os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)


class TestTryLock:
    def test_acquires_an_uncontended_lock(self, lock_file):
        fd = _open(lock_file)
        try:
            assert file_lock.try_lock(fd) is True
        finally:
            file_lock.unlock(fd)
            os.close(fd)

    def test_second_process_is_refused(self, lock_file):
        """The double-click race, with two real processes."""
        fd = _open(lock_file)
        try:
            assert file_lock.try_lock(fd) is True

            script = textwrap.dedent(
                f"""
                import os, sys
                sys.path.insert(0, {os.getcwd()!r})
                from neurobooth_os.util import file_lock
                fd = os.open({str(lock_file)!r}, os.O_RDWR | os.O_CREAT, 0o644)
                sys.exit(0 if file_lock.try_lock(fd) else 3)
                """
            )
            result = subprocess.run([sys.executable, "-c", script], capture_output=True)
            assert result.returncode == 3, (
                f"second process unexpectedly took the lock: {result.stderr.decode()}"
            )
        finally:
            file_lock.unlock(fd)
            os.close(fd)

    def test_lock_is_available_again_after_release(self, lock_file):
        fd = _open(lock_file)
        assert file_lock.try_lock(fd) is True
        file_lock.unlock(fd)
        os.close(fd)

        second = _open(lock_file)
        try:
            assert file_lock.try_lock(second) is True
        finally:
            file_lock.unlock(second)
            os.close(second)

    def test_only_the_first_byte_is_locked(self, lock_file):
        """The holder's PID and start time live from offset 1 and must stay
        readable by a second launch that cannot take the lock."""
        lock_file.write_bytes(b' {"pid": 42}')
        fd = _open(lock_file)
        try:
            assert file_lock.try_lock(fd) is True
            with open(lock_file, "rb") as handle:
                handle.seek(1)
                assert handle.read() == b'{"pid": 42}'
        finally:
            file_lock.unlock(fd)
            os.close(fd)

    def test_leaves_offset_at_start(self, lock_file):
        fd = _open(lock_file)
        try:
            os.lseek(fd, 5, os.SEEK_SET)
            file_lock.try_lock(fd)
            assert os.lseek(fd, 0, os.SEEK_CUR) == 0
        finally:
            file_lock.unlock(fd)
            os.close(fd)

    def test_real_error_propagates(self, lock_file):
        """A bad descriptor is a fault, not contention.

        Returning False here would report "another instance is running" when
        the truth is that the lock file could not be used at all.
        """
        fd = _open(lock_file)
        os.close(fd)
        with pytest.raises(OSError):
            file_lock.try_lock(fd)


class TestUnlock:
    def test_unlocking_an_unheld_lock_is_silent(self, lock_file):
        fd = _open(lock_file)
        try:
            file_lock.unlock(fd)  # never locked
        finally:
            os.close(fd)

    def test_unlocking_a_closed_descriptor_is_silent(self, lock_file):
        """Release runs during teardown, where the fd may already be gone."""
        fd = _open(lock_file)
        os.close(fd)
        file_lock.unlock(fd)
