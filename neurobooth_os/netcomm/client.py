import logging
from time import time, sleep
import os
import subprocess
import ast
import json
import socket
import re

import neurobooth_os.config as cfg


def setup_log(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger


logger = setup_log(__name__)


def _is_local_machine(server_name: str) -> bool:
    """Check if server_name refers to the local machine."""
    if not server_name:
        return False

    hostname = socket.gethostname().upper()
    return server_name.upper() in [hostname, 'LOCALHOST', '127.0.0.1']


def _run_ps_remote_cmd(
        script_block: str, server_name: str, user: str, password: str, timeout: int = 60
) -> str:
    """
    Executes a PowerShell script block on a remote machine using Invoke-Command.
    If the target is the local machine, runs directly without remoting.
    """

    # Check if this is the local machine - if so, run locally
    if _is_local_machine(server_name):
        logger.debug(f"Running PowerShell command locally (detected {server_name} as localhost):\n{script_block}")
        try:
            result = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", script_block],
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
                encoding='utf8'
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(f"Local PowerShell command failed: {e.cmd}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            raise
        except subprocess.TimeoutExpired as e:
            logger.error(f"Local PowerShell command timed out: {e.cmd}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred while running local PowerShell command: {e}")
            raise

    # Remote execution with credentials
    ps_cmd = f"""
    $secpasswd = ConvertTo-SecureString -String '{password}' -AsPlainText -Force
    $credential = New-Object System.Management.Automation.PSCredential ('{user}', $secpasswd)
    Invoke-Command -ComputerName '{server_name}' -Credential $credential -ScriptBlock {{
        {script_block}
    }}
    """

    try:
        logger.debug(f"Running remote PowerShell command on {server_name}:\n{script_block}")
        result = subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
            encoding='utf8'
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Remote PowerShell command failed on {server_name}: {e.cmd}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
        raise
    except subprocess.TimeoutExpired as e:
        logger.error(f"Remote PowerShell command timed out on {server_name}: {e.cmd}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred while running remote PowerShell command: {e}")
        raise


def get_ps_processes(server_name: str, user: str, password: str, process_name: str = "python") -> list:
    """
    Gets a list of processes (PID and CommandLine) from a remote computer.
    """
    script_block = f"""
    $p = Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue;
    if ($p) {{ $p | Select-Object Id, CommandLine | ConvertTo-Json -Compress }}
    """
    try:
        json_output = _run_ps_remote_cmd(script_block, server_name, user, password)
        if not json_output.strip():
            return []

        # PowerShell ConvertTo-Json might output a single object or an array of objects
        processes_data = json.loads(json_output)

        if not isinstance(processes_data, list):
            processes_data = [processes_data]

        result = []
        for p in processes_data:
            result.append({"pid": str(p["Id"]), "commandline": p.get("CommandLine", "")})
        return result

    except Exception as e:
        logger.warning(f"Could not retrieve processes from {server_name}: {e}")
        return []


def kill_ps_remote_pid(pids: list, node_name: str):
    """
    Kills processes on a remote machine using PowerShell's Stop-Process.
    Derives server details from node_name.
    """
    if not pids:
        return

    if node_name not in ["acquisition", "presentation"]:
        logger.warning(f"Node name '{node_name}' not recognized for killing PIDs.")
        return None

    s = cfg.neurobooth_config.server_by_name(node_name)

    # Ensure PIDs are strings for PowerShell
    pid_list_str = ",".join([str(p) for p in pids])

    script_block = f"""
    Stop-Process -Id {pid_list_str} -Force -ErrorAction SilentlyContinue; $null
    """
    try:
        _run_ps_remote_cmd(script_block, s.name, s.user, s.password)
        logger.info(f"Killed PIDs {pids} on {s.name}.")
    except Exception as e:
        logger.warning(f"Failed to kill PIDs {pids} on {s.name}: {e}")


def kill_pid_txt(txt_name="server_pids.txt", node_name=None):
    """
    Reads PIDs from a file, attempts to kill them, and updates the file.
    """
    if not os.path.exists(txt_name):
        return

    with open(txt_name, "r+") as f:
        lines = f.readlines()

        if len(lines):
            print(f"Closing {len(lines)} remote processes recorded in {txt_name}")

        new_lines = []
        for line in lines:
            try:
                pid_str, node, tsmp = line.strip().split("|")
                pid_list = ast.literal_eval(pid_str)

                if node_name is not None and node_name != node:
                    new_lines.append(line)
                    continue

                kill_ps_remote_pid(pid_list, node)
            except Exception as e:
                logger.warning(f"Error processing PID line '{line.strip()}': {e}. Skipping.")
                continue

        f.seek(0)
        if new_lines:
            f.writelines(new_lines)
        else:
            f.write("")
        f.truncate()


def start_server(node_name, save_pid_txt=True):
    """
    Starts a remote server using PowerShell Remoting.
    """
    if node_name not in ["acquisition", "presentation"]:
        print("Not a known node name")
        return None
    s = cfg.neurobooth_config.server_by_name(node_name)

    # 1. Proactively kill any existing relevant Python processes
    expected_script_part = None
    if node_name == "acquisition":
        expected_script_part = "server_acq.py"
    elif node_name == "presentation":
        expected_script_part = "server_stm.py"

    if expected_script_part:
        logger.info(f"Proactively checking for and killing existing '{expected_script_part}' processes on {s.name}.")
        running_python_procs = get_ps_processes(s.name, s.user, s.password, process_name="python")
        pids_to_kill_proactive = []
        for proc in running_python_procs:
            commandline = proc.get('commandline') or ''  # Handle None case
            if expected_script_part in commandline:
                logger.warning(
                    f"Found existing '{expected_script_part}' process (PID: {proc['pid']}). Attempting to kill.")
                pids_to_kill_proactive.append(proc['pid'])
        if pids_to_kill_proactive:
            kill_ps_remote_pid(pids_to_kill_proactive, node_name)

    # 2. Kill any processes recorded in server_pids.txt
    kill_pid_txt(node_name=node_name)

    # 3. Get PIDs before starting new server
    pids_old = [p['pid'] for p in get_ps_processes(s.name, s.user, s.password, process_name="python")]
    logger.debug(f"Python processes found before: {pids_old}")

    # 4. Start the server
    if not s.bat:
        logger.error(f"No .bat file specified for {node_name}. Cannot start server.")
        return None

    bat_path = s.bat

    # Handle environment variables based on whether it's local or remote
    if _is_local_machine(s.name):
        # Local execution - expand environment variables locally
        bat_path = os.path.expandvars(bat_path)
        logger.info(f"Starting {node_name} server locally using: {bat_path}")

        # Check if bat file exists
        if not os.path.exists(bat_path):
            logger.error(f"Batch file does not exist: {bat_path}")
            return None
    else:
        # Remote execution - convert Windows env vars to PowerShell syntax
        # %NB_INSTALL% -> $env:NB_INSTALL
        bat_path = re.sub(r'%(\w+)%', r'$env:\1', bat_path)
        logger.info(f"Starting {node_name} server remotely using: {bat_path}")

    script_block_start = f"""
        Start-Process -FilePath '{bat_path}' -NoNewWindow -PassThru | ConvertTo-Json -Compress
        """
    try:
        start_output = _run_ps_remote_cmd(script_block_start, s.name, s.user, s.password)
        logger.info(f"Triggered start of {bat_path} on {s.name}. Output: {start_output}")
    except Exception as e:
        logger.error(f"Failed to trigger {bat_path} on {s.name}: {e}")
        return None
    sleep(2)

    # 5. Get PIDs after starting new server
    pids_new = [p['pid'] for p in get_ps_processes(s.name, s.user, s.password, process_name="python")]
    logger.debug(f"Python processes found after: {pids_new}")

    pid = [p for p in pids_new if p not in pids_old]
    print(f"{node_name.upper()} server initiated with pid {pid}")
    logger.info(f"{node_name.upper()} server initiated with pid {pid}")

    if save_pid_txt and pid:
        with open("server_pids.txt", "a") as f:
            f.write(f"{pid}|{node_name}|{time()}\n")
    return pid