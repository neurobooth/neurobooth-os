"""Tests for ``neurobooth_os.netcomm.client``.

Covers the three pure / easily-mockable seams:

* ``_build_task_xml`` — branches on ``acq_index`` and ``user``, including
  the ``machine\\user`` qualification fix and XML-escaping of special
  characters in the bat path.
* ``get_all_python_processes_with_cmd`` CSV parsing — pins the two latent
  bugs the WMIC -> Get-CimInstance rewrite (PR #770) called out: column
  ordering and ``str.split(',')`` on quoted CSV.
* ``_read_pid_file`` / ``_write_pid_file`` — pid-file round-trip,
  malformed-line tolerance, and the atomic-write contract.
"""

import subprocess
import xml.etree.ElementTree as ET
from typing import List
from unittest.mock import patch

from neurobooth_os.netcomm import client


# ---------------------------------------------------------------------------
# _build_task_xml
# ---------------------------------------------------------------------------

TASK_NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _parse(xml: str) -> ET.Element:
    """Parse the XML and return the root, asserting it is a Task element."""
    root = ET.fromstring(xml)
    assert root.tag == "{http://schemas.microsoft.com/windows/2004/02/mit/task}Task"
    return root


def test_build_task_xml_no_args_no_user_omits_blocks() -> None:
    xml = client._build_task_xml(r"C:\nb\server_acq.bat", acq_index=None)
    root = _parse(xml)

    # No <Arguments> when acq_index is None
    assert root.find(".//t:Arguments", TASK_NS) is None
    # No <Principals> when user is empty/None
    assert root.find(".//t:Principals", TASK_NS) is None
    # <Actions> has no Context attribute when user is omitted
    actions = root.find(".//t:Actions", TASK_NS)
    assert actions is not None
    assert "Context" not in actions.attrib


def test_build_task_xml_acq_index_zero_emits_arguments() -> None:
    """acq_index=0 must produce an <Arguments> block (the code uses
    ``is not None``, not truthiness — 0 is a valid index)."""
    xml = client._build_task_xml(r"C:\nb\server_acq.bat", acq_index=0)
    root = _parse(xml)
    args = root.find(".//t:Arguments", TASK_NS)
    assert args is not None
    assert args.text == "0"


def test_build_task_xml_acq_index_nonzero() -> None:
    xml = client._build_task_xml(r"C:\nb\server_acq.bat", acq_index=1)
    root = _parse(xml)
    args = root.find(".//t:Arguments", TASK_NS)
    assert args is not None
    assert args.text == "1"


def test_build_task_xml_qualifies_bare_user_with_machine() -> None:
    """A bare username like 'ACQ' must be qualified as 'ACQ\\ACQ' so
    SCHTASKS /S /XML accepts it (the docstring explicitly calls out that
    bare names are rejected as ambiguous)."""
    xml = client._build_task_xml(
        r"C:\nb\server_acq.bat", acq_index=None, user="ACQ", machine="ACQ"
    )
    root = _parse(xml)
    user_id = root.find(".//t:Principals/t:Principal/t:UserId", TASK_NS)
    assert user_id is not None
    assert user_id.text == r"ACQ\ACQ"

    # Actions block must declare Context="Author" when Principals is present
    actions = root.find(".//t:Actions", TASK_NS)
    assert actions is not None
    assert actions.attrib.get("Context") == "Author"


def test_build_task_xml_preserves_already_qualified_user() -> None:
    """A user that already contains a backslash is used as-is (machine
    prefix is not re-applied)."""
    xml = client._build_task_xml(
        r"C:\nb\server_stm.bat", acq_index=None, user=r"DOMAIN\bob", machine="STM"
    )
    root = _parse(xml)
    user_id = root.find(".//t:Principals/t:Principal/t:UserId", TASK_NS)
    assert user_id is not None
    assert user_id.text == r"DOMAIN\bob"


def test_build_task_xml_escapes_xml_special_chars_in_bat_path() -> None:
    """The bat path is interpolated into <Command>; & < > must be escaped
    or the resulting XML is malformed."""
    bat_path = r"C:\nb\weird & path<v2>.bat"
    xml = client._build_task_xml(bat_path, acq_index=None)
    # The point is just that parsing succeeds and the round-tripped value
    # equals the input — ElementTree handles escape/unescape for us.
    root = _parse(xml)
    command = root.find(".//t:Command", TASK_NS)
    assert command is not None
    assert command.text == bat_path


def test_build_task_xml_battery_setting_is_explicit() -> None:
    """The whole reason for /XML over /TR is that SCHTASKS /Create has no
    flag for DisallowStartIfOnBatteries. Pin the value at false."""
    xml = client._build_task_xml(r"C:\nb\server_acq.bat", acq_index=None)
    root = _parse(xml)
    el = root.find(".//t:Settings/t:DisallowStartIfOnBatteries", TASK_NS)
    assert el is not None
    assert el.text == "false"


# ---------------------------------------------------------------------------
# get_all_python_processes_with_cmd CSV parsing
# ---------------------------------------------------------------------------

def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_get_processes_empty_csv_returns_empty() -> None:
    """ConvertTo-Csv with zero processes emits only the header row."""
    csv_out = '"ProcessId","CommandLine"\n'
    with patch.object(client.subprocess, "run", return_value=_completed(csv_out)):
        result = client.get_all_python_processes_with_cmd()
    assert result == []


def test_get_processes_single_row_simple_cmdline() -> None:
    csv_out = (
        '"ProcessId","CommandLine"\n'
        '"1234","python.exe server_acq.py"\n'
    )
    with patch.object(client.subprocess, "run", return_value=_completed(csv_out)):
        result = client.get_all_python_processes_with_cmd()
    assert result == [{"pid": "1234", "commandline": "python.exe server_acq.py"}]


def test_get_processes_cmdline_with_embedded_commas() -> None:
    """The latent bug PR #770 fixed: ``str.split(',')`` broke on command
    lines containing commas. Pin the new ``csv.reader`` behavior."""
    csv_out = (
        '"ProcessId","CommandLine"\n'
        '"5678","python.exe -c \'a,b,c\'"\n'
    )
    with patch.object(client.subprocess, "run", return_value=_completed(csv_out)):
        result = client.get_all_python_processes_with_cmd()
    assert len(result) == 1
    assert result[0]["pid"] == "5678"
    assert "," in result[0]["commandline"]
    assert result[0]["commandline"] == "python.exe -c 'a,b,c'"


def test_get_processes_multiple_rows() -> None:
    csv_out = (
        '"ProcessId","CommandLine"\n'
        '"100","python.exe a.py"\n'
        '"200","python.exe b.py"\n'
        '"300","python.exe c.py"\n'
    )
    with patch.object(client.subprocess, "run", return_value=_completed(csv_out)):
        result = client.get_all_python_processes_with_cmd()
    assert [p["pid"] for p in result] == ["100", "200", "300"]


def test_get_processes_skips_malformed_row(caplog) -> None:
    """A row with fewer than 2 fields is logged and skipped, but does not
    abort the rest of the parse."""
    csv_out = (
        '"ProcessId","CommandLine"\n'
        '"100","python.exe ok.py"\n'
        '"oops"\n'
        '"200","python.exe also_ok.py"\n'
    )
    caplog.set_level("WARNING")
    with patch.object(client.subprocess, "run", return_value=_completed(csv_out)):
        result = client.get_all_python_processes_with_cmd()
    assert [p["pid"] for p in result] == ["100", "200"]
    assert any("Could not parse" in r.message for r in caplog.records)


def test_get_processes_handles_called_process_error(caplog) -> None:
    err = subprocess.CalledProcessError(returncode=1, cmd=[], output="", stderr="boom")
    caplog.set_level("ERROR")
    with patch.object(client.subprocess, "run", side_effect=err):
        result = client.get_all_python_processes_with_cmd()
    assert result == []
    assert any("Get-CimInstance failed" in r.message for r in caplog.records)


def test_get_processes_handles_timeout(caplog) -> None:
    err = subprocess.TimeoutExpired(cmd=[], timeout=30, output="", stderr="")
    caplog.set_level("ERROR")
    with patch.object(client.subprocess, "run", side_effect=err):
        result = client.get_all_python_processes_with_cmd()
    assert result == []
    assert any("timed out" in r.message for r in caplog.records)


def test_get_processes_handles_oserror_on_powershell_launch(caplog) -> None:
    """If ``powershell.exe`` itself can't be launched (FileNotFoundError is
    a subclass of OSError), the function returns ``[]`` rather than
    propagating."""
    caplog.set_level("ERROR")
    with patch.object(
        client.subprocess, "run", side_effect=FileNotFoundError("powershell.exe")
    ):
        result = client.get_all_python_processes_with_cmd()
    assert result == []
    assert any("Failed to launch powershell" in r.message for r in caplog.records)


def test_get_processes_remote_passes_credentials_via_env() -> None:
    """Remote calls must thread credentials through ``env``, not the
    command line. PR #770 explicitly fixes the password-in-cmdline leak."""
    csv_out = '"ProcessId","CommandLine"\n'
    with patch.object(client.subprocess, "run", return_value=_completed(csv_out)) as mock_run:
        client.get_all_python_processes_with_cmd("STM", "stm-user", "secret-pw")

    assert mock_run.call_count == 1
    call = mock_run.call_args
    env = call.kwargs["env"]
    assert env["NB_REMOTE_HOST"] == "STM"
    assert env["NB_REMOTE_USER"] == "stm-user"
    assert env["NB_REMOTE_PASSWORD"] == "secret-pw"

    # Nothing in the actual argv should contain the password.
    argv = call.args[0]
    assert all("secret-pw" not in part for part in argv)


def test_get_processes_local_does_not_set_remote_env() -> None:
    """When server_name/user are absent the local PowerShell snippet runs
    with ``env=None`` (inherits the parent env unchanged)."""
    csv_out = '"ProcessId","CommandLine"\n'
    with patch.object(client.subprocess, "run", return_value=_completed(csv_out)) as mock_run:
        client.get_all_python_processes_with_cmd()

    assert mock_run.call_args.kwargs["env"] is None


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
