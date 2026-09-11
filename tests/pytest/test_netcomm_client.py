"""Tests for ``neurobooth_os.netcomm.client``.

Covers the platform-neutral orchestration that stayed in ``client.py`` after
the OS primitives moved to ``launcher.py``:

* ``_read_pid_file`` / ``_write_pid_file`` — pid-file round-trip,
  malformed-line tolerance, and the atomic-write contract.

The ``_build_task_xml`` and process-listing tests now live in
``test_netcomm_launcher.py``.
"""

from typing import List

from neurobooth_os.netcomm import client


# ---------------------------------------------------------------------------
# _read_pid_file / _write_pid_file
# ---------------------------------------------------------------------------

def test_read_pid_file_missing_returns_empty(tmp_path) -> None:
    assert client._read_pid_file(str(tmp_path / "nope.txt")) == []


def test_pid_file_round_trip(tmp_path) -> None:
    target = tmp_path / "server_pids.txt"
    entries = [("[123, 456]", "acquisition_0", "1700000000.0"),
               ("[789]", "presentation", "1700000010.5")]
    lines = [f"{p}|{n}|{t}\n" for p, n, t in entries]
    client._write_pid_file(lines, str(target))

    assert client._read_pid_file(str(target)) == entries


def test_read_pid_file_skips_malformed_lines(tmp_path, caplog) -> None:
    """Lines without exactly 3 pipe-separated parts are logged and
    skipped; well-formed lines around them survive."""
    target = tmp_path / "server_pids.txt"
    target.write_text(
        "[1]|acquisition_0|123\n"
        "garbage_line_no_pipes\n"
        "only|two\n"
        "[2]|presentation|456\n"
    )
    caplog.set_level("WARNING")
    entries = client._read_pid_file(str(target))
    assert entries == [
        ("[1]", "acquisition_0", "123"),
        ("[2]", "presentation", "456"),
    ]
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("garbage_line_no_pipes" in m for m in warnings)
    assert any("only|two" in m for m in warnings)


def test_read_pid_file_silently_skips_blank_lines(tmp_path, caplog) -> None:
    """Blank lines are not treated as malformed (no warning)."""
    target = tmp_path / "server_pids.txt"
    target.write_text("[1]|acquisition_0|123\n\n[2]|presentation|456\n")
    caplog.set_level("WARNING")
    entries = client._read_pid_file(str(target))
    assert len(entries) == 2
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_write_pid_file_leaves_no_tmp_file(tmp_path) -> None:
    """The atomic-write contract: after _write_pid_file returns, the
    ``.tmp`` sibling must not exist."""
    target = tmp_path / "server_pids.txt"
    client._write_pid_file(["[1]|acquisition_0|123\n"], str(target))
    assert target.exists()
    assert not (tmp_path / "server_pids.txt.tmp").exists()


def test_write_pid_file_overwrites_existing(tmp_path) -> None:
    """``os.replace`` overwrites the destination on Windows + POSIX alike."""
    target = tmp_path / "server_pids.txt"
    target.write_text("old content\n")
    client._write_pid_file(["new|content|now\n"], str(target))
    assert target.read_text() == "new|content|now\n"


def test_pid_file_round_trip_preserves_order(tmp_path) -> None:
    """Order is part of the contract: kill_pid_txt iterates the list and
    the most-recent entries are appended at the end."""
    target = tmp_path / "server_pids.txt"
    entries: List = [
        (f"[{i}]", "acquisition_0", str(1_700_000_000 + i)) for i in range(5)
    ]
    client._write_pid_file([f"{p}|{n}|{t}\n" for p, n, t in entries], str(target))
    assert client._read_pid_file(str(target)) == entries
