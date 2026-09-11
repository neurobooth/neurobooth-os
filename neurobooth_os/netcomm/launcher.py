# -*- coding: utf-8 -*-
"""Platform backends for starting, listing and killing the server processes.

The control GUI brings up the acquisition and presentation servers and later
tears them down. On Windows that is done through the Task Scheduler, because a
CLI-created task inherits ``DisallowStartIfOnBatteries=true`` and would sit
queued forever on a laptop running on battery -- ``SCHTASKS /Create /XML`` is
the only way to set that flag. None of those primitives exist off Windows.

This module isolates the three OS-level operations behind
:class:`ProcessLauncher` so the orchestration in :mod:`neurobooth_os.netcomm.client`
-- PID bookkeeping, before/after process diffing, the ``server_pids.txt`` file --
stays platform-neutral:

* :meth:`ProcessLauncher.list_python_processes`
* :meth:`ProcessLauncher.launch`
* :meth:`ProcessLauncher.kill`

:class:`WindowsLauncher` carries the existing SCHTASKS / tasklist /
``Get-CimInstance`` implementation unchanged, so booth behaviour does not move.
:class:`PosixLauncher` uses ``psutil`` and :mod:`subprocess`, which is enough
for the single-machine development and mock sessions macOS and Linux are
targeted at.
"""

import abc
import csv
import io
import logging
import os
import re
import subprocess
import sys
import tempfile
import xml.sax.saxutils as _saxutils
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

# Route through the "app" logger so messages reach the PostgreSQLHandler
# attached by make_db_logger (log_manager.py). A privately-named logger
# (e.g. logging.getLogger(__name__)) has no handlers attached and no
# propagation path to the "app" logger, so its messages are silently
# dropped — that's why SCHTASKS / Get-CimInstance failures used to vanish.
logger = logging.getLogger("app")


class ProcessInfo(NamedTuple):
    """One running Python process, as reported by a launcher backend."""

    pid: str
    commandline: str


#: Import path of the module each node runs. The POSIX backend launches these
#: with ``python -m``; the Windows backend reaches them through the node's
#: ``.bat``, which invokes the same file by path.
NODE_MODULES: Dict[str, str] = {
    "acquisition": "neurobooth_os.server_acq",
    "presentation": "neurobooth_os.server_stm",
}


def node_base_name(node_name: str) -> str:
    """Reduce ``'acquisition_1'`` to ``'acquisition'``; pass others through."""
    return "acquisition" if node_name.startswith("acquisition") else node_name


def node_process_token(node_name: str) -> Optional[str]:
    """Return a substring that identifies this node's process on any platform.

    Windows command lines name the script (``server_acq.py``); POSIX ones name
    the module (``neurobooth_os.server_acq``). ``server_acq`` is a substring of
    both, so one token matches either form.

    Args:
        node_name: A node name such as ``'acquisition_0'`` or ``'presentation'``.

    Returns:
        The token, or ``None`` for a node with no server process.
    """
    module = NODE_MODULES.get(node_base_name(node_name))
    return module.rsplit(".", 1)[-1] if module else None


class ProcessLauncher(abc.ABC):
    """The OS-level operations the server lifecycle needs."""

    @abc.abstractmethod
    def list_python_processes(self, service) -> List[ProcessInfo]:
        """List Python processes on the machine hosting ``service``.

        Args:
            service: A ``ResolvedService`` naming the host and, for remote
                execution, the credentials to reach it.

        Returns:
            One :class:`ProcessInfo` per Python process. An empty list on
            failure -- callers treat enumeration as best-effort.
        """

    @abc.abstractmethod
    def launch(self, service, node_name: str, acq_index: Optional[int]) -> None:
        """Start the server process for ``node_name`` on ``service``'s machine.

        Args:
            service: The ``ResolvedService`` for the node.
            node_name: e.g. ``'acquisition_0'`` or ``'presentation'``.
            acq_index: Index passed to the acquisition server, or ``None``.
        """

    @abc.abstractmethod
    def kill(self, service, pids: List[str]) -> None:
        """Terminate ``pids`` on ``service``'s machine.

        Failures are logged rather than raised: a PID that has already exited
        is the normal teardown race, not an error.
        """


def _is_remote(service) -> bool:
    """True when this service must be reached over the network.

    An empty ``user`` is the single-machine shortcut documented in
    docs/single_machine_testing.md: run everything here, no credentials.
    """
    return bool(service.name and service.user)


def _service_password(service) -> Optional[str]:
    return service.password.get_secret_value() if service.password else None


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


def _run_cmd(cmd_list: list, server_name: str = None, user: str = None, password: str = None,
             error_level: int = logging.ERROR) -> str:
    """Run a subprocess command and return its stdout.

    Args:
        cmd_list: The command and arguments to run.
        server_name, user, password: For remote execution via /S /U /P.
        error_level: Log level used when the command fails or times out.
            Defaults to ERROR. Callers wrapping benign-failure operations
            (e.g. taskkill where the target PID may already be gone) can
            pass ``logging.WARNING`` to keep log_application uncluttered.
    """
    full_cmd = list(cmd_list)
    # Single-machine testing: an empty user means "run on this machine" — skip
    # /S /U /P so tasklist/SCHTASKS execute locally. See
    # docs/single_machine_testing.md.
    if server_name and user:
        full_cmd = full_cmd[:1] + ["/S", server_name, "/U", user, "/P", password] + full_cmd[1:]

    try:
        logger.debug(f"Running command: {' '.join(cmd_list)} (on {server_name or 'localhost'})")
        result = subprocess.run(full_cmd, capture_output=True, text=True, check=True, timeout=30)
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.log(error_level,
                   f"Command failed (on {server_name or 'localhost'}): {' '.join(cmd_list)}, "
                   f"stdout: {e.stdout}, stderr: {e.stderr}")
        raise
    except subprocess.TimeoutExpired as e:
        logger.log(error_level,
                   f"Command timed out (on {server_name or 'localhost'}): {' '.join(cmd_list)}, "
                   f"stdout: {e.stdout}, stderr: {e.stderr}")
        raise


_PS_REMOTE_GET_PYTHON_PROCESSES = r"""
$ErrorActionPreference = 'Stop'
$securepw = ConvertTo-SecureString $env:NB_REMOTE_PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($env:NB_REMOTE_USER, $securepw)
$opt = New-CimSessionOption -Protocol Dcom
$sess = New-CimSession -ComputerName $env:NB_REMOTE_HOST -Credential $cred -SessionOption $opt
try {
    Get-CimInstance -CimSession $sess -ClassName Win32_Process -Filter "Name='python.exe'" |
        Select-Object ProcessId, CommandLine |
        ConvertTo-Csv -NoTypeInformation
} finally {
    Remove-CimSession $sess
}
"""

_PS_LOCAL_GET_PYTHON_PROCESSES = r"""
$ErrorActionPreference = 'Stop'
Get-CimInstance -ClassName Win32_Process -Filter "Name='python.exe'" |
    Select-Object ProcessId, CommandLine |
    ConvertTo-Csv -NoTypeInformation
"""


def _build_task_xml(bat_path: str, acq_index: Optional[int],
                    user: Optional[str] = None,
                    machine: Optional[str] = None,
                    unqualified_user: bool = False) -> str:
    """Build a Task Scheduler XML for an event-triggered server task.

    SCHTASKS /Create has no CLI flag for the battery-condition setting, so a
    CLI-created task inherits the Windows default DisallowStartIfOnBatteries=true
    and silently sits in "Queued" on a laptop running on battery (the .bat
    never launches). /Create /XML lets us write that setting explicitly.

    The trigger keys off Application Event ID 777 — nothing emits that event;
    it exists only so /Run can launch the task on demand.

    When ``user`` is provided, a <Principals> block is included so SCHTASKS
    /S /XML accepts the file: remote task creation requires an explicit
    UserId, and the /TR flow that this code replaced got it from /U
    automatically. The UserId is qualified as ``machine\\user`` unless
    ``user`` already contains a backslash or ``unqualified_user`` is set
    (IP-addressed host), in which case the bare ``user`` is used. Local
    creation (no /S) auto-fills Principals, so we omit the block when
    ``user`` is empty/None.
    """
    command = _saxutils.escape(bat_path)
    args_block = ""
    if acq_index is not None:
        args_block = f"      <Arguments>{_saxutils.escape(str(acq_index))}</Arguments>\n"

    principals_block = ""
    actions_open = "  <Actions>\n"
    if user:
        # Qualify with the target machine name when not already domain-qualified.
        # Bare "ACQ" is rejected by Task Scheduler XML validation as ambiguous;
        # "ACQ\\ACQ" (which is what /Query shows for the existing task) is not.
        if unqualified_user:
            # IP-addressed host: emit the bare user, unqualified.
            qualified_user = user
        elif "\\" not in user and machine:
            qualified_user = f"{machine}\\{user}"
        else:
            qualified_user = user
        user_escaped = _saxutils.escape(qualified_user)
        principals_block = (
            '  <Principals>\n'
            '    <Principal id="Author">\n'
            f'      <UserId>{user_escaped}</UserId>\n'
            '      <LogonType>InteractiveToken</LogonType>\n'
            '      <RunLevel>LeastPrivilege</RunLevel>\n'
            '    </Principal>\n'
            '  </Principals>\n'
        )
        actions_open = '  <Actions Context="Author">\n'

    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <Triggers>\n'
        '    <EventTrigger>\n'
        '      <Enabled>true</Enabled>\n'
        "      <Subscription>&lt;QueryList&gt;&lt;Query&gt;&lt;Select Path='Application'&gt;"
        "*[System/EventID=777]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>\n"
        '    </EventTrigger>\n'
        '  </Triggers>\n'
        f'{principals_block}'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <AllowStartOnDemand>true</AllowStartOnDemand>\n'
        '    <Enabled>true</Enabled>\n'
        '    <ExecutionTimeLimit>PT72H</ExecutionTimeLimit>\n'
        '  </Settings>\n'
        f'{actions_open}'
        '    <Exec>\n'
        f'      <Command>{command}</Command>\n'
        f'{args_block}'
        '    </Exec>\n'
        '  </Actions>\n'
        '</Task>\n'
    )


class WindowsLauncher(ProcessLauncher):
    """Task Scheduler / tasklist / Get-CimInstance backend.

    This is the booth implementation. Nothing here changed when the abstraction
    was introduced; it was moved verbatim out of ``client.py``.
    """

    def list_python_processes(self, service) -> List[ProcessInfo]:
        # Remote calls use a DCOM CimSession to match the wire protocol WMIC used,
        # so the existing inter-machine WMI/firewall/registry runbook in
        # docs/inter_machine_setup.md remains the source of truth. WSMan/WinRM
        # is deliberately not used (different security model — see #760).
        #
        # Credentials are passed via env vars so the password never appears in the
        # process command line (strictly more secure than the previous WMIC call,
        # which exposed it via /PASSWORD:).
        if _is_remote(service):
            ps_command = _PS_REMOTE_GET_PYTHON_PROCESSES
            ps_env = {
                **os.environ,
                "NB_REMOTE_HOST": service.name,
                "NB_REMOTE_USER": service.user,
                "NB_REMOTE_PASSWORD": _service_password(service) or "",
            }
        else:
            # Single-machine testing: empty user → run locally.
            # See docs/single_machine_testing.md.
            ps_command = _PS_LOCAL_GET_PYTHON_PROCESSES
            ps_env = None

        host = service.name or "localhost"
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_command]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=30, env=ps_env
            )
            output = result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(
                f"Get-CimInstance failed (on {host}): stdout: {e.stdout}, stderr: {e.stderr}"
            )
            return []
        except subprocess.TimeoutExpired as e:
            logger.error(
                f"Get-CimInstance timed out (on {host}): stdout: {e.stdout}, stderr: {e.stderr}"
            )
            return []
        except OSError as e:
            logger.error(f"Failed to launch powershell.exe: {e}")
            return []

        # ConvertTo-Csv -NoTypeInformation emits one header row followed by one
        # row per object: "ProcessId","CommandLine". csv.reader handles quoted
        # fields and embedded commas correctly (which the previous naive
        # str.split(',') did not).
        processes: List[ProcessInfo] = []
        rows = list(csv.reader(io.StringIO(output)))
        if len(rows) <= 1:
            return processes
        for row in rows[1:]:
            if len(row) >= 2:
                processes.append(ProcessInfo(pid=row[0].strip(), commandline=row[1].strip()))
            else:
                logger.warning(f"Could not parse Get-CimInstance output row: {row}")
        return processes

    def list_python_pids(self, service) -> List[str]:
        """PIDs only, via ``tasklist``.

        Kept distinct from :meth:`list_python_processes` because ``tasklist``
        is markedly cheaper than a CIM query and ``start_server`` calls this
        twice per launch just to diff before against after.
        """
        try:
            output = _run_cmd(
                ["tasklist.exe"], service.name, service.user, _service_password(service)
            )
        except Exception:
            return []

        re_pyth = re.compile("python.exe[\\s]*([0-9]*)")
        pids = []
        for prc in output.split("\n"):
            srch = re_pyth.search(prc)
            if srch is not None:
                pids.append(srch.groups()[0])
        return pids

    def launch(self, service, node_name: str, acq_index: Optional[int]) -> None:
        password = _service_password(service)
        task_name = self._next_free_task_name(service, password)

        # Always (re)create via /XML /F. /F overwrites stale tasks left by older
        # versions of this code that used /TR — those were created with the
        # default DisallowStartIfOnBatteries=true and would queue forever on a
        # laptop on battery. See _build_task_xml for the schema we apply.
        logger.info(f"Creating Windows task: {task_name}")
        xml_content = _build_task_xml(
            service.bat, acq_index, user=service.user, machine=service.name,
            unqualified_user=service.unqualified_user,
        )
        fd, xml_path = tempfile.mkstemp(suffix='.xml')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(b'\xff\xfe')  # SCHTASKS /XML expects UTF-16 LE with BOM
                f.write(xml_content.encode('utf-16-le'))
            _run_cmd(
                ["SCHTASKS", "/Create", "/TN", task_name, "/XML", xml_path, "/F"],
                service.name, service.user, password,
            )
        finally:
            try:
                os.remove(xml_path)
            except OSError:
                pass

        _run_cmd(["SCHTASKS", "/Run", "/TN", task_name], service.name, service.user, password)

    def _next_free_task_name(self, service, password: Optional[str]) -> str:
        """Pick a task name that is not currently running.

        The scheduler refuses to re-run a task that is already running, so a
        numeric suffix is bumped until a free name is found.
        """
        try:
            query_output = _run_cmd(
                ["SCHTASKS", "/query", "/fo", "CSV", "/nh"],
                service.name, service.user, password,
            )
        except Exception:
            query_output = ""  # No scheduled tasks, or the command failed.

        scheduled_tasks = {}
        for line in query_output.strip().split("\n"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                scheduled_tasks[parts[0].strip('"').lstrip('\\')] = parts[1].strip('"')

        task_name = service.task_name + "0"
        while task_name in scheduled_tasks and scheduled_tasks[task_name] == "Running":
            try:
                task_name = task_name[:-1] + str(int(task_name[-1]) + 1)
            except ValueError:  # Name does not end with a digit.
                task_name += "_1"
        return task_name

    def kill(self, service, pids: List[str]) -> None:
        password = _service_password(service)
        for pid in pids:
            # taskkill commonly "fails" because the PID has already exited (the
            # normal teardown race); downgrade the subprocess-level log to
            # WARNING so log_application isn't filled with ERROR rows for the
            # benign case. The caller-level WARN below carries the per-PID context.
            try:
                _run_cmd(
                    ["taskkill", "/PID", str(pid), "/F"],
                    service.name, service.user, password, error_level=logging.WARNING,
                )
                logger.info(f"Killed PID {pid} on {service.name} server.")
            except Exception as e:
                logger.warning(f"Failed to kill PID {pid} on {service.name} server: {e}")


# ---------------------------------------------------------------------------
# POSIX
# ---------------------------------------------------------------------------


class RemoteLaunchUnsupported(NotImplementedError):
    """Raised when a POSIX host is asked to drive a remote machine.

    The Windows backend reaches other booths over DCOM and SMB. There is no
    POSIX equivalent in place; ssh via paramiko is the intended route when a
    multi-machine deployment actually needs it. Single-machine development and
    mock sessions, which is what macOS and Linux are targeted at, never take
    this path -- they run with an empty ``user``.
    """


class PosixLauncher(ProcessLauncher):
    """psutil + subprocess backend for macOS and Linux.

    Local operation only. Remote calls raise :class:`RemoteLaunchUnsupported`
    rather than failing obscurely part-way through a session.
    """

    def _reject_remote(self, service, operation: str) -> None:
        if _is_remote(service):
            raise RemoteLaunchUnsupported(
                f"Cannot {operation} on remote host '{service.name}' from "
                f"{sys.platform}. Remote server control is implemented for "
                f"Windows only. For single-machine use, set the machine's "
                f"'user' to \"\" in neurobooth_os_config.yaml."
            )

    def list_python_processes(self, service) -> List[ProcessInfo]:
        self._reject_remote(service, "list processes")
        import psutil

        processes: List[ProcessInfo] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                name = proc.info.get("name") or ""
                # Match the interpreter by executable name or argv[0]; a venv
                # interpreter is still called python3.13, python, or similar.
                first = os.path.basename(cmdline[0]) if cmdline else ""
                if not ("python" in name.lower() or "python" in first.lower()):
                    continue
                processes.append(
                    ProcessInfo(pid=str(proc.info["pid"]), commandline=" ".join(cmdline))
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # The process exited between iteration and inspection, or
                # belongs to another user. Neither is ours to report.
                continue
        return processes

    def list_python_pids(self, service) -> List[str]:
        return [p.pid for p in self.list_python_processes(service)]

    def launch(self, service, node_name: str, acq_index: Optional[int]) -> None:
        self._reject_remote(service, "start a server")
        module = NODE_MODULES.get(node_base_name(node_name))
        if module is None:
            raise ValueError(f"No server module is defined for node '{node_name}'.")

        command = [sys.executable, "-m", module]
        if acq_index is not None:
            command.append(str(acq_index))

        log_handle = self._open_log(service, node_name)
        try:
            # start_new_session detaches the child from this process group, so
            # a Ctrl-C in the GUI's terminal does not take the servers with it.
            # That mirrors what `start /W` gives the .bat launcher on Windows.
            subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        finally:
            if log_handle not in (None, subprocess.DEVNULL):
                # The child holds its own duplicate of the descriptor.
                log_handle.close()
        logger.info(f"Launched {' '.join(command)} for node {node_name}")

    def _open_log(self, service, node_name: str):
        """Open this node's stdout log, falling back to discarding output.

        The Windows launcher gives each server its own console window. There is
        no console here, so the output goes to a file next to the application
        logs; losing it entirely would make a failed launch invisible.
        """
        log_dir = getattr(service, "local_log_dir", None)
        if not log_dir:
            return subprocess.DEVNULL
        try:
            directory = Path(os.path.expanduser(str(log_dir)))
            directory.mkdir(parents=True, exist_ok=True)
            return open(directory / f"{node_name}_stdout.log", "ab")
        except OSError as e:
            logger.warning(
                f"Could not open a stdout log for {node_name} in {log_dir}: {e}. "
                f"Server output will be discarded."
            )
            return subprocess.DEVNULL

    def kill(self, service, pids: List[str]) -> None:
        self._reject_remote(service, "kill a process")
        import psutil

        for pid in pids:
            try:
                process = psutil.Process(int(pid))
            except (psutil.NoSuchProcess, ValueError) as e:
                # Already gone, or a malformed entry in server_pids.txt. Both
                # are the ordinary teardown case, not a failure worth raising.
                logger.warning(f"No process to kill for PID {pid}: {e}")
                continue
            try:
                process.terminate()
                process.wait(timeout=5)
                logger.info(f"Terminated PID {pid} on {service.name or 'localhost'}.")
            except psutil.TimeoutExpired:
                logger.warning(f"PID {pid} ignored SIGTERM; sending SIGKILL.")
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    pass
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.warning(f"Failed to kill PID {pid}: {e}")


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

_launcher_override: Optional[ProcessLauncher] = None


def get_launcher() -> ProcessLauncher:
    """Return the launcher backend for this platform.

    Tests can force a backend with :func:`set_launcher`; production code never
    passes one, so the selection stays in a single place.
    """
    if _launcher_override is not None:
        return _launcher_override
    return WindowsLauncher() if sys.platform == "win32" else PosixLauncher()


def set_launcher(launcher: Optional[ProcessLauncher]) -> None:
    """Override the backend :func:`get_launcher` returns. ``None`` restores it."""
    global _launcher_override
    _launcher_override = launcher
