import logging
from time import time, sleep
import re
import os
import subprocess
import ast
from typing import List, Tuple

import neurobooth_os.config as cfg


def setup_log(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger


logger = setup_log(__name__)


def _run_cmd(cmd_list: list, server_name: str = None, user: str = None, password: str = None) -> str:
    full_cmd = list(cmd_list)
    if server_name:
        executable = full_cmd[0].upper()
        if executable == "WMIC":
            # WMIC uses /NODE:, /USER:, /PASSWORD: instead of /S, /U, /P
            full_cmd = full_cmd[:1] + [
                f"/NODE:{server_name}", f"/USER:{user}", f"/PASSWORD:{password}"
            ] + full_cmd[1:]
        else:
            full_cmd = full_cmd[:1] + ["/S", server_name, "/U", user, "/P", password] + full_cmd[1:]

    try:
        logger.debug(f"Running command: {' '.join(cmd_list)} (on {server_name or 'localhost'})")
        result = subprocess.run(full_cmd, capture_output=True, text=True, check=True, timeout=30)
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed (on {server_name or 'localhost'}): {' '.join(cmd_list)}, "
                     f"stdout: {e.stdout}, stderr: {e.stderr}")
        raise
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out (on {server_name or 'localhost'}): {' '.join(cmd_list)}, "
                     f"stdout: {e.stdout}, stderr: {e.stderr}")
        raise


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
    cmd_args = ["WMIC", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine", "/FORMAT:CSV"]
    try:
        output_wmic = _run_cmd(cmd_args, server_name, user, password)
    except Exception:
        return []

    processes = []
    # Skip the first line (header) and the last empty line
    lines = output_wmic.strip().split("\n")
    if len(lines) > 1:
        for line in lines[1:]:  # Skip header
            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    pid = parts[0].strip()
                    cmd_line = parts[1].strip()
                    processes.append({"pid": pid, "commandline": cmd_line})
                except ValueError:
                    logger.warning(f"Could not parse WMIC output line: {line}")
    return processes


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
    if s.password is None:
        raise cfg.ConfigException(
            f"Cannot start remote server '{node_name}': no password configured. "
            f"Service passwords are required in secrets.yaml on the control machine."
        )

    # Identify and kill any existing Python processes for this node
    expected_script = None
    if node_name.startswith("acquisition"):
        expected_script = "server_acq.py"
    elif node_name == "presentation":
        expected_script = "server_stm.py"

    if expected_script:
        logger.info(f"Proactively checking for and killing existing '{expected_script}' processes on {node_name}.")
        running_python_procs = get_all_python_processes_with_cmd(s.name, s.user, s.password.get_secret_value())
        for proc in running_python_procs:
            if expected_script in proc.get('commandline', ''):
                logger.warning(f"Found existing '{expected_script}' process (PID: {proc['pid']}). Attempting to kill.")
                kill_remote_pid([proc['pid']], node_name)
    
    # Kill any previous server that were recorded
    kill_pid_txt(node_name=node_name)

    # Get list of python processes before starting new one
    pids_old = get_python_pids(s.name, s.user, s.password.get_secret_value())
    logger.debug(f"Python processes found before: {pids_old}")

    # Get list of scheduled tasks and run TaskOnEvent if not running
    try:
        schtasks_query_output = _run_cmd(["SCHTASKS", "/query", "/fo", "CSV", "/nh"], s.name, s.user, s.password.get_secret_value())
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

    cmd_schtasks_base = ["SCHTASKS"]

    if task_name not in scheduled_tasks:
        print(f"Windows task: {task_name} was not found. Attempting to create")
        # Inner quotes around the bat path ensure subprocess quoting
        # produces \"path\" arg on the command line, so SCHTASKS stores
        # the bat as the executable and the index as a separate argument.
        # Without inner quotes, the space-containing value gets wrapped
        # as "path arg" — SCHTASKS treats the whole thing as the program
        # path and the argument is lost.
        tr_cmd = f'"{s.bat}" {acq_index}' if acq_index is not None else s.bat
        cmd_1 = cmd_schtasks_base + [
            "/Create", "/TN", task_name, "/TR", tr_cmd, "/SC", "ONEVENT", "/EC", "Application", "/MO", "*[System/EventID=777]", "/f"
        ]
        _run_cmd(cmd_1, s.name, s.user, s.password.get_secret_value())

    cmd_2 = cmd_schtasks_base + ["/Run", "/TN", task_name]
    _run_cmd(cmd_2, s.name, s.user, s.password.get_secret_value())

    sleep(0.3)
    pids_new = get_python_pids(s.name, s.user, s.password.get_secret_value())
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
    if s.password is None:
        raise cfg.ConfigException(
            f"Cannot kill remote process on '{node_name}': no password configured. "
            f"Service passwords are required in secrets.yaml on the control machine."
        )

    if isinstance(pids, str):
        pids = [pids]

    for pid in pids:
        cmd_args = ["taskkill", "/PID", str(pid), "/F"]
        # _run_cmd handles adding remote credentials if s.name is not None
        try:
            _run_cmd(cmd_args, s.name, s.user, s.password.get_secret_value())
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