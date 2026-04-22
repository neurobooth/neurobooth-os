"""Tests for the single-instance GUI lock (issue #510).

The cross-process race test uses a **subprocess**, NOT a same-process
second acquire. Windows byte-range lock semantics for two handles in the
same process are historically documented as "undefined" by Microsoft and
differ across Windows editions. The real-world scenario the lock protects
against is always two separate processes (double-click race), so the test
exercises that path directly. Do not simplify this to a same-process
re-acquire — it can appear to pass on one Windows SKU and fail on another.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="msvcrt byte-range locks are Windows-only",
)


@pytest.fixture
def lock_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NB_INSTALL", str(tmp_path))
    import neurobooth_os.gui as gui_mod
    monkeypatch.setattr(gui_mod, "_GUI_LOCK_FD", None)
    monkeypatch.setattr(gui_mod, "_GUI_LOCK_PATH", None)
    yield tmp_path
    if gui_mod._GUI_LOCK_FD is not None:
        try:
            os.close(gui_mod._GUI_LOCK_FD)
        except OSError:
            pass


def test_acquire_writes_lock_file_and_locks_it(lock_env):
    import neurobooth_os.gui as gui_mod

    result = gui_mod._acquire_gui_lock()

    try:
        assert result.acquired is True
        assert result.path == str(lock_env / "gui.lock")
        assert result.holder_pid == os.getpid()
        assert result.reason is None

        lock_path = lock_env / "gui.lock"
        assert lock_path.exists()

        with open(lock_path, "rb") as f:
            f.seek(1)
            payload = json.loads(f.read().decode("utf-8"))
        assert payload["pid"] == os.getpid()
        datetime.fromisoformat(payload["started"])
    finally:
        gui_mod._release_gui_lock(result)


def test_second_acquire_is_refused_via_subprocess(lock_env):
    import neurobooth_os.gui as gui_mod

    helper = (
        'import os, msvcrt, json, sys\n'
        'from datetime import datetime, timezone\n'
        'path = os.path.join(os.environ["NB_INSTALL"], "gui.lock")\n'
        'fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)\n'
        'os.lseek(fd, 0, os.SEEK_SET)\n'
        'msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)\n'
        'payload = json.dumps({"pid": os.getpid(), '
        '"started": datetime.now(timezone.utc).isoformat()}).encode("utf-8")\n'
        'os.lseek(fd, 0, os.SEEK_SET)\n'
        'os.write(fd, b" " + payload)\n'
        'os.ftruncate(fd, 1 + len(payload))\n'
        'os.fsync(fd)\n'
        'print("ACQUIRED", flush=True)\n'
        'sys.stdin.read()\n'
    )

    env = os.environ.copy()
    env["NB_INSTALL"] = str(lock_env)

    proc = subprocess.Popen(
        [sys.executable, "-c", helper],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        first_line = proc.stdout.readline().strip()
        assert first_line == "ACQUIRED", (
            f"subprocess did not acquire lock (got {first_line!r}); "
            f"stderr: {proc.stderr.read()!r}"
        )

        result = gui_mod._acquire_gui_lock()
        assert result.acquired is False
        assert result.reason == "locked"
        assert result.holder_pid == proc.pid
        assert result.holder_started is not None
        datetime.fromisoformat(result.holder_started)
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_stale_lock_file_allows_reacquire(lock_env):
    import neurobooth_os.gui as gui_mod

    lock_path = lock_env / "gui.lock"
    stale_payload = json.dumps(
        {"pid": 99999, "started": "2020-01-01T00:00:00+00:00"}
    ).encode("utf-8")
    lock_path.write_bytes(b" " + stale_payload)

    result = gui_mod._acquire_gui_lock()

    try:
        assert result.acquired is True
        assert result.holder_pid == os.getpid()

        with open(lock_path, "rb") as f:
            f.seek(1)
            payload = json.loads(f.read().decode("utf-8"))
        assert payload["pid"] == os.getpid()
        assert payload["pid"] != 99999
    finally:
        gui_mod._release_gui_lock(result)


def test_release_unlinks_file_and_clears_state(lock_env):
    import neurobooth_os.gui as gui_mod

    result = gui_mod._acquire_gui_lock()
    assert result.acquired is True
    lock_path = lock_env / "gui.lock"
    assert lock_path.exists()

    gui_mod._release_gui_lock(result)

    assert not lock_path.exists()
    assert gui_mod._GUI_LOCK_FD is None
    assert gui_mod._GUI_LOCK_PATH is None


def test_release_is_idempotent_and_noop_on_failed_acquire(lock_env):
    import neurobooth_os.gui as gui_mod

    gui_mod._release_gui_lock(None)

    gui_mod._release_gui_lock(
        gui_mod.GuiLockResult(acquired=False, path="doesnotexist")
    )

    result = gui_mod._acquire_gui_lock()
    gui_mod._release_gui_lock(result)
    gui_mod._release_gui_lock(result)


def test_acquire_returns_open_failed_on_permission_error(lock_env, monkeypatch):
    import neurobooth_os.gui as gui_mod

    monkeypatch.setattr(
        "os.open",
        MagicMock(side_effect=PermissionError("denied")),
    )

    result = gui_mod._acquire_gui_lock()

    assert result.acquired is False
    assert result.reason is not None
    assert result.reason.startswith("open_failed:")
    assert "denied" in result.reason


def test_signal_gui_to_activate_returns_false_on_none_pid():
    import neurobooth_os.gui as gui_mod

    assert gui_mod._signal_gui_to_activate(None) is False
