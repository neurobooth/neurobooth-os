import logging
from time import time, sleep
import re
import os
import subprocess
import ast
import csv
import io
from typing import List, Optional, Tuple

import neurobooth_os.config as cfg
from neurobooth_os.deploy import schtasks


# Route through the "app" logger so messages reach the PostgreSQLHandler
# attached by make_db_logger (log_manager.py). A privately-named logger
# (e.g. logging.getLogger(__name__)) has no handlers attached and no
# propagation path to the "app" logger, so its messages are silently
# dropped — that's why SCHTASKS / Get-CimInstance failures used to vanish.
logger = logging.getLogger("app")


# Moved to neurobooth_os.deploy.schtasks so the deploy tool can use it without
# importing the booth config stack; kept under the old name for callers here.
_run_cmd = schtasks.run_cmd


def get_python_pids(server_name: str = None, user: str = None, password: str = None) -> list:
    """Gets a list of Python process IDs from the local or remote computer.

    Parameters
    ----------
    server_name : str, optional
        Name of the remote server. If None, gets local PIDs.
    user : str, optional
        Username for remote server.
    password : str, optional
        Password for remote server.

    Returns
    -------
    list
        List of Python process identifiers.
    """
    cmd_args = ["tasklist.exe"]
    # _run_cmd handles adding remote credentials if server_name is not None
    try:
        output_tasklist = _run_cmd(cmd_args, server_name, user, password)
    except Exception:
        return []

    procs = output_tasklist.split("\n")
    re_pyth = re.compile("python.exe[\\s]*([0-9]*)")

    pyth_pids = []
    for prc in procs:
        srch = re_pyth.search(prc)
        if srch is not None:
            pyth_pids.append(srch.groups()[0])
    return pyth_pids


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


def get_all_python_processes_with_cmd(server_name: str = None, user: str = None, password: str = None) -> list:
    """Gets a list of Python process IDs and their command lines from the local or remote computer.

    Parameters
    ----------
    server_name : str, optional
        Name of the remote server. If None, gets local PIDs.
    user : str, optional
        Username for remote server.
    password : str, optional
        Password for remote server.

    Returns
    -------
    list
        List of dictionaries, each with 'pid' and 'commandline' for Python processes.
    """
    # Remote calls use a DCOM CimSession to match the wire protocol WMIC used,
    # so the existing inter-machine WMI/firewall/registry runbook in
    # docs/inter_machine_setup.md remains the source of truth. WSMan/WinRM
    # is deliberately not used (different security model — see #760).
    #
    # Credentials are passed via env vars so the password never appears in the
    # process command line (strictly more secure than the previous WMIC call,
    # which exposed it via /PASSWORD:).
    if server_name and user:
        ps_command = _PS_REMOTE_GET_PYTHON_PROCESSES
        ps_env = {
            **os.environ,
            "NB_REMOTE_HOST": server_name,
            "NB_REMOTE_USER": user,
            "NB_REMOTE_PASSWORD": password or "",
        }
    else:
        # Single-machine testing: empty user → run locally.
        # See docs/single_machine_testing.md.
        ps_command = _PS_LOCAL_GET_PYTHON_PROCESSES
        ps_env = None

    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_command]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=30, env=ps_env
        )
        output = result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Get-CimInstance failed (on {server_name or 'localhost'}): "
            f"stdout: {e.stdout}, stderr: {e.stderr}"
        )
        return []
    except subprocess.TimeoutExpired as e:
        logger.error(
            f"Get-CimInstance timed out (on {server_name or 'localhost'}): "
            f"stdout: {e.stdout}, stderr: {e.stderr}"
        )
        return []
    except OSError as e:
        logger.error(f"Failed to launch powershell.exe: {e}")
        return []

    # ConvertTo-Csv -NoTypeInformation emits one header row followed by one
    # row per object: "ProcessId","CommandLine". csv.reader handles quoted
    # fields and embedded commas correctly (which the previous naive
    # str.split(',') did not).
    processes = []
    rows = list(csv.reader(io.StringIO(output)))
    if len(rows) <= 1:
        return processes
    for row in rows[1:]:
        if len(row) >= 2:
            processes.append({"pid": row[0].strip(), "commandline": row[1].strip()})
        else:
            logger.warning(f"Could not parse Get-CimInstance output row: {row}")
    return processes


def _build_task_xml(bat_path: str, acq_index: Optional[int],
                    user: Optional[str] = None,
                    machine: Optional[str] = None,
                    unqualified_user: bool = False) -> str:
    """Build the Task Scheduler XML for a booth server task.

    Thin adapter over :func:`neurobooth_os.deploy.schtasks.build_task_xml`:
    the acquisition index becomes the .bat argument.
    """
    arguments = str(acq_index) if acq_index is not None else None
    return schtasks.build_task_xml(bat_path, arguments, user=user, machine=machine,
                                   unqualified_user=unqualified_user)


def start_server(node_name, acq_index=None, save_pid_txt=True):
    """Makes a network call to run script serv_{node_name}.bat

    First remote processes are logged, then a scheduled task is created to run
    the remote batch file, then task runs, and new python PIDs are captured with
    the option to save to save_pid_txt. If saved, when the function is called it
    will kill the PIDs in the file.

    Parameters
    ----------
    node_name : str
        PC node name, e.g. 'acquisition_0', 'acquisition_1', 'presentation'.
    acq_index : int, optional
        Index of the acquisition server. Required for acquisition nodes.
    save_pid_txt : bool
        Option to save PID to file for killing PID in the future.

    Returns
    -------
    pid : list
        Python process identifiers found in remote computer after server started.
    """

    if not (node_name.startswith("acquisition") or node_name == "presentation"):
        print("Not a known node name")
        return None
    s = cfg.neurobooth_config.server_by_name(node_name)
    if s.user and s.password is None:
        raise cfg.ConfigException(
            f"Cannot start remote server '{node_name}': no password configured. "
            f"Service passwords are required in secrets.yaml on the control machine."
        )
    pwd = s.password.get_secret_value() if s.password else None

    # Identify and kill any existing Python processes for this node
    expected_script = None
    if node_name.startswith("acquisition"):
        expected_script = "server_acq.py"
    elif node_name == "presentation":
        expected_script = "server_stm.py"

    if expected_script:
        logger.info(f"Proactively checking for and killing existing '{expected_script}' processes on {node_name}.")
        running_python_procs = get_all_python_processes_with_cmd(s.name, s.user, pwd)
        for proc in running_python_procs:
            if expected_script in proc.get('commandline', ''):
                logger.warning(f"Found existing '{expected_script}' process (PID: {proc['pid']}). Attempting to kill.")
                kill_remote_pid([proc['pid']], node_name)

    # Kill any previous server that were recorded
    kill_pid_txt(node_name=node_name)

    # Get list of python processes before starting new one
    pids_old = get_python_pids(s.name, s.user, pwd)
    logger.debug(f"Python processes found before: {pids_old}")

    # Get list of scheduled tasks and run TaskOnEvent if not running
    try:
        schtasks_query_output = _run_cmd(["SCHTASKS", "/query", "/fo", "CSV", "/nh"], s.name, s.user, pwd)
    except Exception:
        schtasks_query_output = "" # No scheduled tasks or command failed

    # Manual parsing of CSV output
    scheduled_tasks = {}
    for line in schtasks_query_output.strip().split("\n"):
        parts = line.strip().split(",")
        if len(parts) >= 2:
            task_name = parts[0].strip('"').lstrip('\\')
            status = parts[1].strip('"')
            scheduled_tasks[task_name] = {"status": status}

    # task_name is the name of the task to create & run in the remote server's Windows Task Scheduler
    task_name = s.task_name + "0"
    print(f"Preparing to run windows task: {task_name}")
    while True:
        if task_name in scheduled_tasks:
            print(f"{task_name} was found")
            # if task already running add n+1 to task name
            if scheduled_tasks[task_name]["status"] == "Running":
                try:
                    tsk_inx = int(task_name[-1]) + 1
                    task_name = task_name[:-1] + str(tsk_inx)
                    print(f"Creating new scheduled task: {task_name} in server {node_name}")
                except ValueError: # Handle cases where task_name doesn't end with a number
                    task_name += "_1"
                    print(f"Creating new scheduled task: {task_name} in server {node_name}")
                continue
        break

    # Always (re)create via /XML /F. /F overwrites stale tasks left by older
    # versions of this code that used /TR — those were created with the
    # default DisallowStartIfOnBatteries=true and would queue forever on a
    # laptop on battery. See _build_task_xml for the schema we apply.
    print(f"Creating Windows task: {task_name}")
    xml_content = _build_task_xml(s.bat, acq_index, user=s.user, machine=s.name,
                                  unqualified_user=s.unqualified_user)
    schtasks.create_task(task_name, xml_content, s.name, s.user, pwd)
    schtasks.run_task(task_name, s.name, s.user, pwd)

    sleep(0.3)
    pids_new = get_python_pids(s.name, s.user, pwd)
    logger.debug(f"Python processes found after: {pids_new}")

    pid = [p for p in pids_new if p not in pids_old]
    print(f"{node_name.upper()} server initiated with pid {pid}")
    logger.info(f"{node_name.upper()} server initiated with pid {pid}")

    if save_pid_txt:
        entries = _read_pid_file()
        entries.append((str(pid), node_name, str(time())))
        _write_pid_file([f"{p}|{n}|{t}\n" for p, n, t in entries])
    return pid


def _read_pid_file(txt_name: str = "server_pids.txt") -> List[Tuple[str, str, str]]:
    """Read and validate server_pids.txt, skipping malformed lines."""
    if not os.path.exists(txt_name):
        return []
    entries = []
    with open(txt_name, "r") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) != 3:
                if line.strip():  # Only warn on non-blank lines
                    logger.warning(f"Skipping malformed line in {txt_name}: {line.strip()!r}")
                continue
            entries.append((parts[0], parts[1], parts[2]))
    return entries


def _write_pid_file(lines: List[str], txt_name: str = "server_pids.txt") -> None:
    """Write server_pids.txt atomically via temp file + rename."""
    tmp_name = txt_name + ".tmp"
    with open(tmp_name, "w") as f:
        f.writelines(lines)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_name, txt_name)


def kill_remote_pid(pids, node_name):

    if not (node_name.startswith("acquisition") or node_name == "presentation"):
        print("Not a known node name")
        return None

    s = cfg.neurobooth_config.server_by_name(node_name)
    if s.user and s.password is None:
        raise cfg.ConfigException(
            f"Cannot kill remote process on '{node_name}': no password configured. "
            f"Service passwords are required in secrets.yaml on the control machine."
        )
    pwd = s.password.get_secret_value() if s.password else None

    if isinstance(pids, str):
        pids = [pids]

    for pid in pids:
        cmd_args = ["taskkill", "/PID", str(pid), "/F"]
        # _run_cmd handles adding remote credentials if s.name is not None.
        # taskkill commonly "fails" because the PID has already exited (the
        # normal teardown race); downgrade the subprocess-level log to
        # WARNING so log_application isn't filled with ERROR rows for the
        # benign case. The caller-level WARN below carries the per-PID context.
        try:
            _run_cmd(cmd_args, s.name, s.user, pwd, error_level=logging.WARNING)
            logger.info(f"Killed PID {pid} on {node_name} server.")
        except Exception as e:
            logger.warning(f"Failed to kill PID {pid} on {node_name} server: {e}")
    return


def kill_pid_txt(txt_name="server_pids.txt", node_name=None):
    entries = _read_pid_file(txt_name)
    if not entries:
        return

    print(f"Closing {len(entries)} remote processes")

    remaining = []
    for pid, node, tsmp in entries:
        if node_name is not None and node_name != node:
            remaining.append((pid, node, tsmp))
            continue
        try:
            kill_remote_pid(ast.literal_eval(pid), node)
        except (IndexError, cfg.ConfigException) as e:
            logger.warning(f"Skipping stale pid entry {pid} for {node}: {e}")

    if remaining:
        _write_pid_file([f"{p}|{n}|{t}\n" for p, n, t in remaining], txt_name)
    elif os.path.exists(txt_name):
        os.remove(txt_name)