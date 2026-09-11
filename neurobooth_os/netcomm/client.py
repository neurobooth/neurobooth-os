# -*- coding: utf-8 -*-
"""Server lifecycle orchestration: start a node, track its PIDs, kill it later.

The OS-level primitives live in :mod:`neurobooth_os.netcomm.launcher`, which
picks a Windows or POSIX backend. Everything here -- the before/after process
diff, the ``server_pids.txt`` bookkeeping, the proactive kill of a stale server
-- is platform-neutral and runs identically on both.
"""

import ast
import logging
import os
from time import time, sleep
from typing import List, Optional, Tuple

import neurobooth_os.config as cfg
from neurobooth_os.netcomm.launcher import (
    ProcessInfo,
    get_launcher,
    node_process_token,
)

# Route through the "app" logger so messages reach the PostgreSQLHandler
# attached by make_db_logger (log_manager.py). A privately-named logger
# (e.g. logging.getLogger(__name__)) has no handlers attached and no
# propagation path to the "app" logger, so its messages are silently
# dropped — that's why SCHTASKS / Get-CimInstance failures used to vanish.
logger = logging.getLogger("app")

PID_FILE = "server_pids.txt"


def _known_node(node_name: str) -> bool:
    return node_name.startswith("acquisition") or node_name == "presentation"


def _service_for(node_name: str, operation: str):
    """Resolve a node to its service, rejecting a missing remote password.

    Args:
        node_name: e.g. ``'acquisition_0'``.
        operation: Phrase used in the error message, e.g. ``'start remote server'``.

    Raises:
        ConfigException: If the service names a remote user but has no password.
    """
    service = cfg.neurobooth_config.server_by_name(node_name)
    if service.user and service.password is None:
        raise cfg.ConfigException(
            f"Cannot {operation} '{node_name}': no password configured. "
            f"Service passwords are required in secrets.yaml on the control machine."
        )
    return service


def get_python_pids(node_name: str) -> List[str]:
    """Python process IDs on the machine hosting ``node_name``."""
    return get_launcher().list_python_pids(_service_for(node_name, "list processes on"))


def get_all_python_processes_with_cmd(node_name: str) -> List[ProcessInfo]:
    """Python processes, with command lines, on the machine hosting ``node_name``."""
    launcher = get_launcher()
    return launcher.list_python_processes(_service_for(node_name, "list processes on"))


def start_server(node_name, acq_index=None, save_pid_txt=True):
    """Start the server process for a node and record its PIDs.

    Any process already running this node's server is killed first, then the
    node is launched and the new Python PIDs are captured by diffing the
    process list before against after.

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
        Python process identifiers that appeared after the server started.
    """
    if not _known_node(node_name):
        logger.error(f"Not a known node name: {node_name}")
        return None

    service = _service_for(node_name, "start server on")
    launcher = get_launcher()

    # Identify and kill any existing server process for this node.
    token = node_process_token(node_name)
    if token:
        logger.info(f"Checking for and killing existing '{token}' processes on {node_name}.")
        for proc in launcher.list_python_processes(service):
            if token in proc.commandline:
                logger.warning(
                    f"Found existing '{token}' process (PID: {proc.pid}). Attempting to kill."
                )
                kill_remote_pid([proc.pid], node_name)

    # Kill any previous server that was recorded.
    kill_pid_txt(node_name=node_name)

    pids_old = launcher.list_python_pids(service)
    logger.debug(f"Python processes found before: {pids_old}")

    launcher.launch(service, node_name, acq_index)

    sleep(0.3)
    pids_new = launcher.list_python_pids(service)
    logger.debug(f"Python processes found after: {pids_new}")

    pid = [p for p in pids_new if p not in pids_old]
    logger.info(f"{node_name.upper()} server initiated with pid {pid}")

    if save_pid_txt:
        entries = _read_pid_file()
        entries.append((str(pid), node_name, str(time())))
        _write_pid_file([f"{p}|{n}|{t}\n" for p, n, t in entries])
    return pid


def _read_pid_file(txt_name: str = PID_FILE) -> List[Tuple[str, str, str]]:
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


def _write_pid_file(lines: List[str], txt_name: str = PID_FILE) -> None:
    """Write server_pids.txt atomically via temp file + rename."""
    tmp_name = txt_name + ".tmp"
    with open(tmp_name, "w") as f:
        f.writelines(lines)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_name, txt_name)


def kill_remote_pid(pids, node_name) -> None:
    """Kill the given PIDs on the machine hosting ``node_name``.

    Named for the multi-machine case, but it covers the local one too: the
    launcher backend decides whether the node is reachable in-process or over
    the network.
    """
    if not _known_node(node_name):
        logger.error(f"Not a known node name: {node_name}")
        return None

    service = _service_for(node_name, "kill remote process on")
    if isinstance(pids, str):
        pids = [pids]
    get_launcher().kill(service, [str(p) for p in pids])


def kill_pid_txt(txt_name: str = PID_FILE, node_name: Optional[str] = None) -> None:
    """Kill every PID recorded in the PID file, optionally for one node only."""
    entries = _read_pid_file(txt_name)
    if not entries:
        return

    logger.info(f"Closing {len(entries)} recorded server processes")

    remaining = []
    for pid, node, tsmp in entries:
        if node_name is not None and node_name != node:
            remaining.append((pid, node, tsmp))
            continue
        try:
            kill_remote_pid(ast.literal_eval(pid), node)
        except (IndexError, ValueError, SyntaxError, cfg.ConfigException) as e:
            logger.warning(f"Skipping stale pid entry {pid} for {node}: {e}")

    if remaining:
        _write_pid_file([f"{p}|{n}|{t}\n" for p, n, t in remaining], txt_name)
    elif os.path.exists(txt_name):
        os.remove(txt_name)
