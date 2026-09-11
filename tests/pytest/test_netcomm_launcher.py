"""Tests for ``neurobooth_os.netcomm.launcher``.

These moved here from ``test_netcomm_client.py`` when the OS-level primitives
were split out of ``client.py`` behind the :class:`ProcessLauncher` interface.
The assertions are unchanged; only the import path and the return type (a
:class:`ProcessInfo` namedtuple rather than a bare dict) differ.

* ``_build_task_xml`` — branches on ``acq_index`` and ``user``, including
  the ``machine\\user`` qualification fix and XML-escaping of special
  characters in the bat path.
* ``WindowsLauncher.list_python_processes`` CSV parsing — pins the two latent
  bugs the WMIC -> Get-CimInstance rewrite (PR #770) called out: column
  ordering and ``str.split(',')`` on quoted CSV.
* ``PosixLauncher`` — process filtering, local-only guard, and the module
  command it builds for each node.
"""

import subprocess
import sys
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from neurobooth_os.netcomm import launcher
from neurobooth_os.netcomm.launcher import (
    PosixLauncher,
    ProcessInfo,
    RemoteLaunchUnsupported,
    WindowsLauncher,
    node_process_token,
)


def _service(name: str = "", user: str = "", password: str = None, **kwargs):
    """Build a stand-in for ResolvedService.

    An empty ``user`` is the single-machine shortcut: run here, no credentials.
    """
    secret = SimpleNamespace(get_secret_value=lambda: password) if password else None
    fields = dict(
        name=name, user=user, password=secret, bat=r"C:\nb\server_acq.bat",
        task_name="acquisition", unqualified_user=False, local_log_dir=None,
    )
    fields.update(kwargs)
    return SimpleNamespace(**fields)


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
    xml = launcher._build_task_xml(r"C:\nb\server_acq.bat", acq_index=None)
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
    xml = launcher._build_task_xml(r"C:\nb\server_acq.bat", acq_index=0)
    root = _parse(xml)
    args = root.find(".//t:Arguments", TASK_NS)
    assert args is not None
    assert args.text == "0"


def test_build_task_xml_acq_index_nonzero() -> None:
    xml = launcher._build_task_xml(r"C:\nb\server_acq.bat", acq_index=1)
    root = _parse(xml)
    args = root.find(".//t:Arguments", TASK_NS)
    assert args is not None
    assert args.text == "1"


def test_build_task_xml_qualifies_bare_user_with_machine() -> None:
    """A bare username like 'ACQ' must be qualified as 'ACQ\\ACQ' so
    SCHTASKS /S /XML accepts it (the docstring explicitly calls out that
    bare names are rejected as ambiguous)."""
    xml = launcher._build_task_xml(
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


def test_build_task_xml_unqualified_user_emits_bare_user() -> None:
    """When unqualified_user is set (IP-addressed host), the bare user is
    emitted instead of the 'machine\\user' qualified form."""
    xml = launcher._build_task_xml(
        r"C:\nb\server_acq.bat", acq_index=None, user="ACQ",
        machine="192.0.2.10", unqualified_user=True,
    )
    root = _parse(xml)
    user_id = root.find(".//t:Principals/t:Principal/t:UserId", TASK_NS)
    assert user_id is not None
    assert user_id.text == "ACQ"


def test_build_task_xml_preserves_already_qualified_user() -> None:
    """A user that already contains a backslash is used as-is (machine
    prefix is not re-applied)."""
    xml = launcher._build_task_xml(
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
    xml = launcher._build_task_xml(bat_path, acq_index=None)
    # The point is just that parsing succeeds and the round-tripped value
    # equals the input — ElementTree handles escape/unescape for us.
    root = _parse(xml)
    command = root.find(".//t:Command", TASK_NS)
    assert command is not None
    assert command.text == bat_path


def test_build_task_xml_battery_setting_is_explicit() -> None:
    """The whole reason for /XML over /TR is that SCHTASKS /Create has no
    flag for DisallowStartIfOnBatteries. Pin the value at false."""
    xml = launcher._build_task_xml(r"C:\nb\server_acq.bat", acq_index=None)
    root = _parse(xml)
    el = root.find(".//t:Settings/t:DisallowStartIfOnBatteries", TASK_NS)
    assert el is not None
    assert el.text == "false"


# ---------------------------------------------------------------------------
# WindowsLauncher.list_python_processes CSV parsing
# ---------------------------------------------------------------------------

def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_get_processes_empty_csv_returns_empty() -> None:
    """ConvertTo-Csv with zero processes emits only the header row."""
    csv_out = '"ProcessId","CommandLine"\n'
    with patch.object(launcher.subprocess, "run", return_value=_completed(csv_out)):
        result = WindowsLauncher().list_python_processes(_service())
    assert result == []


def test_get_processes_single_row_simple_cmdline() -> None:
    csv_out = (
        '"ProcessId","CommandLine"\n'
        '"1234","python.exe server_acq.py"\n'
    )
    with patch.object(launcher.subprocess, "run", return_value=_completed(csv_out)):
        result = WindowsLauncher().list_python_processes(_service())
    assert result == [ProcessInfo(pid="1234", commandline="python.exe server_acq.py")]


def test_get_processes_cmdline_with_embedded_commas() -> None:
    """The latent bug PR #770 fixed: ``str.split(',')`` broke on command
    lines containing commas. Pin the new ``csv.reader`` behavior."""
    csv_out = (
        '"ProcessId","CommandLine"\n'
        '"5678","python.exe -c \'a,b,c\'"\n'
    )
    with patch.object(launcher.subprocess, "run", return_value=_completed(csv_out)):
        result = WindowsLauncher().list_python_processes(_service())
    assert len(result) == 1
    assert result[0].pid == "5678"
    assert "," in result[0].commandline
    assert result[0].commandline == "python.exe -c 'a,b,c'"


def test_get_processes_multiple_rows() -> None:
    csv_out = (
        '"ProcessId","CommandLine"\n'
        '"100","python.exe a.py"\n'
        '"200","python.exe b.py"\n'
        '"300","python.exe c.py"\n'
    )
    with patch.object(launcher.subprocess, "run", return_value=_completed(csv_out)):
        result = WindowsLauncher().list_python_processes(_service())
    assert [p.pid for p in result] == ["100", "200", "300"]


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
    with patch.object(launcher.subprocess, "run", return_value=_completed(csv_out)):
        result = WindowsLauncher().list_python_processes(_service())
    assert [p.pid for p in result] == ["100", "200"]
    assert any("Could not parse" in r.message for r in caplog.records)


def test_get_processes_handles_called_process_error(caplog) -> None:
    err = subprocess.CalledProcessError(returncode=1, cmd=[], output="", stderr="boom")
    caplog.set_level("ERROR")
    with patch.object(launcher.subprocess, "run", side_effect=err):
        result = WindowsLauncher().list_python_processes(_service())
    assert result == []
    assert any("Get-CimInstance failed" in r.message for r in caplog.records)


def test_get_processes_handles_timeout(caplog) -> None:
    err = subprocess.TimeoutExpired(cmd=[], timeout=30, output="", stderr="")
    caplog.set_level("ERROR")
    with patch.object(launcher.subprocess, "run", side_effect=err):
        result = WindowsLauncher().list_python_processes(_service())
    assert result == []
    assert any("timed out" in r.message for r in caplog.records)


def test_get_processes_handles_oserror_on_powershell_launch(caplog) -> None:
    """If ``powershell.exe`` itself can't be launched (FileNotFoundError is
    a subclass of OSError), the function returns ``[]`` rather than
    propagating."""
    caplog.set_level("ERROR")
    with patch.object(
        launcher.subprocess, "run", side_effect=FileNotFoundError("powershell.exe")
    ):
        result = WindowsLauncher().list_python_processes(_service())
    assert result == []
    assert any("Failed to launch powershell" in r.message for r in caplog.records)


def test_get_processes_remote_passes_credentials_via_env() -> None:
    """Remote calls must thread credentials through ``env``, not the
    command line. PR #770 explicitly fixes the password-in-cmdline leak."""
    csv_out = '"ProcessId","CommandLine"\n'
    with patch.object(launcher.subprocess, "run", return_value=_completed(csv_out)) as mock_run:
        WindowsLauncher().list_python_processes(_service("STM", "stm-user", "secret-pw"))

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
    with patch.object(launcher.subprocess, "run", return_value=_completed(csv_out)) as mock_run:
        WindowsLauncher().list_python_processes(_service())

    assert mock_run.call_args.kwargs["env"] is None



# ---------------------------------------------------------------------------
# node_process_token
# ---------------------------------------------------------------------------


class TestNodeProcessToken:
    @pytest.mark.parametrize(
        "node,expected",
        [
            ("acquisition", "server_acq"),
            ("acquisition_0", "server_acq"),
            ("acquisition_2", "server_acq"),
            ("presentation", "server_stm"),
        ],
    )
    def test_known_nodes(self, node, expected):
        assert node_process_token(node) == expected

    def test_token_matches_both_platform_command_line_shapes(self):
        """One token has to match the Windows script and the POSIX module.

        Windows command lines name ``server_acq.py``; POSIX ones name
        ``neurobooth_os.server_acq``. If this ever stops holding, start_server
        silently fails to kill a stale server.
        """
        token = node_process_token("acquisition_0")
        assert token in r"C:\nb\python.exe C:\nb\neurobooth_os\server_acq.py 0"
        assert token in "/venv/bin/python -m neurobooth_os.server_acq 0"

    def test_node_without_a_server_returns_none(self):
        assert node_process_token("control") is None


# ---------------------------------------------------------------------------
# PosixLauncher
# ---------------------------------------------------------------------------


class TestPosixLauncherRemoteGuard:
    """A POSIX host cannot drive another machine, and must say so plainly."""

    REMOTE = dict(name="ACQ", user="acq-user", password="pw")

    def test_list_rejects_remote(self):
        with pytest.raises(RemoteLaunchUnsupported, match="ACQ"):
            PosixLauncher().list_python_processes(_service(**self.REMOTE))

    def test_launch_rejects_remote(self):
        with pytest.raises(RemoteLaunchUnsupported):
            PosixLauncher().launch(_service(**self.REMOTE), "acquisition_0", 0)

    def test_kill_rejects_remote(self):
        with pytest.raises(RemoteLaunchUnsupported):
            PosixLauncher().kill(_service(**self.REMOTE), ["123"])

    def test_error_names_the_single_machine_escape_hatch(self):
        with pytest.raises(RemoteLaunchUnsupported) as excinfo:
            PosixLauncher().list_python_processes(_service(**self.REMOTE))
        assert "user" in str(excinfo.value)

    def test_named_host_with_empty_user_is_local(self):
        """A machine may be named and still be this one -- user:"" says so."""
        with patch.object(launcher, "_is_remote", return_value=False):
            PosixLauncher()._reject_remote(_service(name="ACQ", user=""), "test")


class TestPosixLauncherProcessListing:
    @staticmethod
    def _proc(pid, name, cmdline):
        return SimpleNamespace(info={"pid": pid, "name": name, "cmdline": cmdline})

    def _run(self, procs, monkeypatch):
        fake_psutil = MagicMock()
        fake_psutil.process_iter.return_value = procs
        fake_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
        monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
        return PosixLauncher().list_python_processes(_service())

    def test_keeps_python_processes(self, monkeypatch):
        procs = [self._proc(1, "python3.13", ["/v/bin/python3.13", "-m", "neurobooth_os.server_acq"])]
        result = self._run(procs, monkeypatch)
        assert result == [
            ProcessInfo(pid="1", commandline="/v/bin/python3.13 -m neurobooth_os.server_acq")
        ]

    def test_drops_non_python_processes(self, monkeypatch):
        procs = [
            self._proc(1, "Finder", ["/System/Finder"]),
            self._proc(2, "python", ["/usr/bin/python", "x.py"]),
        ]
        assert [p.pid for p in self._run(procs, monkeypatch)] == ["2"]

    def test_matches_on_argv_when_name_is_unhelpful(self, monkeypatch):
        """A renamed or wrapped interpreter still shows up in argv[0]."""
        procs = [self._proc(7, "", ["/opt/python3.11", "-m", "neurobooth_os.server_stm"])]
        assert [p.pid for p in self._run(procs, monkeypatch)] == ["7"]

    def test_empty_cmdline_is_skipped(self, monkeypatch):
        procs = [self._proc(9, "", None)]
        assert self._run(procs, monkeypatch) == []


class TestPosixLauncherLaunch:
    def test_builds_module_command_with_index(self):
        with patch.object(launcher.subprocess, "Popen") as popen:
            PosixLauncher().launch(_service(), "acquisition_1", 1)
        argv = popen.call_args.args[0]
        assert argv == [sys.executable, "-m", "neurobooth_os.server_acq", "1"]

    def test_omits_index_when_none(self):
        with patch.object(launcher.subprocess, "Popen") as popen:
            PosixLauncher().launch(_service(), "presentation", None)
        assert popen.call_args.args[0] == [sys.executable, "-m", "neurobooth_os.server_stm"]

    def test_index_zero_is_passed_not_dropped(self):
        """0 is falsy; an `if acq_index:` test here would silently lose it."""
        with patch.object(launcher.subprocess, "Popen") as popen:
            PosixLauncher().launch(_service(), "acquisition_0", 0)
        assert popen.call_args.args[0][-1] == "0"

    def test_detaches_from_this_process_group(self):
        """Ctrl-C in the GUI's terminal must not take the servers with it."""
        with patch.object(launcher.subprocess, "Popen") as popen:
            PosixLauncher().launch(_service(), "presentation", None)
        assert popen.call_args.kwargs["start_new_session"] is True

    def test_unknown_node_raises(self):
        with pytest.raises(ValueError, match="control"):
            PosixLauncher().launch(_service(), "control", None)

    def test_output_discarded_when_no_log_dir(self):
        with patch.object(launcher.subprocess, "Popen") as popen:
            PosixLauncher().launch(_service(local_log_dir=None), "presentation", None)
        assert popen.call_args.kwargs["stdout"] == subprocess.DEVNULL

    def test_writes_stdout_log_when_log_dir_set(self, tmp_path):
        service = _service(local_log_dir=str(tmp_path))
        with patch.object(launcher.subprocess, "Popen"):
            PosixLauncher().launch(service, "presentation", None)
        assert (tmp_path / "presentation_stdout.log").exists()

    def test_unwritable_log_dir_falls_back_to_devnull(self, tmp_path, caplog):
        caplog.set_level("WARNING")
        blocked = tmp_path / "blocked"
        blocked.write_text("not a directory")
        with patch.object(launcher.subprocess, "Popen") as popen:
            PosixLauncher().launch(_service(local_log_dir=str(blocked)), "presentation", None)
        assert popen.call_args.kwargs["stdout"] == subprocess.DEVNULL
        assert any("discarded" in r.message for r in caplog.records)


class TestPosixLauncherKill:
    def _psutil(self, monkeypatch, process):
        fake = MagicMock()
        fake.Process.return_value = process
        fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        fake.AccessDenied = type("AccessDenied", (Exception,), {})
        fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
        monkeypatch.setitem(sys.modules, "psutil", fake)
        return fake

    def test_terminates_then_waits(self, monkeypatch):
        proc = MagicMock()
        self._psutil(monkeypatch, proc)
        PosixLauncher().kill(_service(), ["321"])
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once()
        proc.kill.assert_not_called()

    def test_escalates_to_sigkill_on_timeout(self, monkeypatch):
        proc = MagicMock()
        fake = self._psutil(monkeypatch, proc)
        proc.wait.side_effect = fake.TimeoutExpired()
        PosixLauncher().kill(_service(), ["321"])
        proc.kill.assert_called_once()

    def test_already_exited_is_not_an_error(self, monkeypatch, caplog):
        """The teardown race is normal; it must warn, not raise."""
        caplog.set_level("WARNING")
        fake = MagicMock()
        fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        fake.AccessDenied = type("AccessDenied", (Exception,), {})
        fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
        fake.Process.side_effect = fake.NoSuchProcess()
        monkeypatch.setitem(sys.modules, "psutil", fake)
        PosixLauncher().kill(_service(), ["321"])
        assert any("No process to kill" in r.message for r in caplog.records)

    def test_malformed_pid_is_skipped(self, monkeypatch, caplog):
        caplog.set_level("WARNING")
        fake = MagicMock()
        fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        fake.AccessDenied = type("AccessDenied", (Exception,), {})
        fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
        monkeypatch.setitem(sys.modules, "psutil", fake)
        PosixLauncher().kill(_service(), ["not-a-pid"])
        assert any("No process to kill" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


class TestGetLauncher:
    def test_picks_windows_on_win32(self, monkeypatch):
        monkeypatch.setattr(launcher.sys, "platform", "win32")
        assert isinstance(launcher.get_launcher(), WindowsLauncher)

    @pytest.mark.parametrize("platform", ["darwin", "linux"])
    def test_picks_posix_elsewhere(self, monkeypatch, platform):
        monkeypatch.setattr(launcher.sys, "platform", platform)
        assert isinstance(launcher.get_launcher(), PosixLauncher)

    def test_override_wins_and_is_reversible(self):
        sentinel = WindowsLauncher()
        launcher.set_launcher(sentinel)
        try:
            assert launcher.get_launcher() is sentinel
        finally:
            launcher.set_launcher(None)
        assert launcher.get_launcher() is not sentinel
