import logging
from time import time, sleep
import re
import subprocess
import ast
from io import StringIO
import json

import neurobooth_os.config as cfg


def setup_log(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger


logger = setup_log(__name__)


def _run_ps_remote_cmd(
    script_block: str, server_name: str, user: str, password: str, timeout: int = 60
) -> str:
    """
    Executes a PowerShell script block on a remote machine using Invoke-Command.
    """
    # Create a secure credential object on the remote machine context.
    # Note: Passing password as plain text in the command line is generally insecure.
    # For production, consider using saved credentials, PSSessions, or more secure methods.
    
    ps_cmd = f"""
    $secpasswd = ConvertTo-SecureString -String '{password}' -AsPlainText -Force
    $credential = New-Object System.Management.Automation.PSCredential ('{user}', $secpasswd)
    Invoke-Command -ComputerName '{server_name}' -Credential $credential -ScriptBlock {{
        {script_block}
    }}
    """
    
    try:
        logger.debug(f"Running remote PowerShell command on {server_name}:\n{script_block}")
        # Execute the PowerShell command locally to invoke remotely
        result = subprocess.run(
            ["powershell.exe", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
            encoding='utf8' # Ensure proper encoding for PowerShell output
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
    Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue |
    Select-Object Id, CommandLine |
    ConvertTo-Json -Compress
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


def kill_ps_remote_pid(pids: list, server_name: str, user: str, password: str):
    """
    Kills processes on a remote machine using PowerShell's Stop-Process.
    """
    if not pids:
        return

    # Ensure PIDs are strings for PowerShell
    pid_list_str = ",".join([str(p) for p in pids])

    script_block = f"""
    Stop-Process -Id {pid_list_str} -Force -ErrorAction SilentlyContinue
    """
    try:
        _run_ps_remote_cmd(script_block, server_name, user, password)
        logger.info(f"Killed PIDs {pids} on {server_name}.")
    except Exception as e:
        logger.warning(f"Failed to kill PIDs {pids} on {server_name}: {e}")


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
                # Remove brackets from pid_str before literal_eval
                pid_list = ast.literal_eval(pid_str) 

                if node_name is not None and node_name != node:
                    new_lines.append(line)
                    continue
                
                # Get server config to pass to kill_ps_remote_pid
                s = cfg.neurobooth_config.server_by_name(node)
                kill_ps_remote_pid(pid_list, s.name, s.user, s.password)
            except Exception as e:
                logger.warning(f"Error processing PID line '{line.strip()}': {e}. Skipping.")
                # If there's an error, assume it's an old/invalid entry and don't re-add it.
                continue

        f.seek(0)
        if new_lines:
            f.writelines(new_lines)
        else:
            f.write("") # Clear the file if all PIDs were handled or none left
        f.truncate()


def start_server_ps(node_name, save_pid_txt=True):
    """
    Starts a remote server using PowerShell Remoting.
    """
    if node_name not in ["acquisition", "presentation"]:
        print("Not a known node name")
        return None
    s = cfg.neurobooth_config.server_by_name(node)

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
            if expected_script_part in proc.get('commandline', ''):
                logger.warning(f"Found existing '{expected_script_part}' process (PID: {proc['pid']}). Attempting to kill.")
                pids_to_kill_proactive.append(proc['pid'])
        if pids_to_kill_proactive:
            kill_ps_remote_pid(pids_to_kill_proactive, s.name, s.user, s.password)

    # 2. Kill any processes recorded in server_pids.txt
    kill_pid_txt(node_name=node_name)

    # 3. Get PIDs before starting new server
    pids_old = [p['pid'] for p in get_ps_processes(s.name, s.user, s.password, process_name="python")]
    logger.debug(f"Python processes found before: {pids_old}")

    # 4. Start the server directly executing the Python script
    # Assuming s.bat is a path like "C:\\path\\to\\neurobooth_os\\server_acq.py"
    # Or, if s.bat just runs a script, we directly execute that script.
    
    # Heuristic for script path (this might need refinement based on actual s.bat content)
    script_to_execute = os.path.join(s.local_data_dir, "neurobooth_os", f"{node_name}", f"server_{node_name}.py")
    if node_name == "acquisition":
         script_to_execute = os.path.join(s.local_data_dir, "neurobooth_os", "server_acq.py")
    elif node_name == "presentation":
         script_to_execute = os.path.join(s.local_data_dir, "neurobooth_os", "server_stm.py")
    # This might need to be 'python.exe' depending on remote PATH
    # The current s.bat likely sets up the environment and runs the script.
    # For direct execution, we need to ensure the correct python.exe is used.
    # A safer approach might be to still trigger the .bat file via PowerShell,
    # but that re-introduces the .bat dependency.

    # Let's assume for now python is in PATH and the script is accessible
    # This part would need actual path to the Python executable on remote machine.
    # For now, let's just trigger the original .bat file via PowerShell for consistency.
    
    if not s.bat:
        logger.error(f"No .bat file specified for {node_name}. Cannot start server.")
        return None

    # Execute the .bat file directly via PowerShell
    # This uses Start-Process which runs asynchronously and detaches.
    script_block_start = f"""
    Start-Process -FilePath '{s.bat}' -NoNewWindow -PassThru | ConvertTo-Json -Compress
    """
    try:
        # Note: Start-Process with -NoNewWindow might not produce immediate PID if it's a batch script launching another process
        # We rely on checking Get-Process later to find the new Python PID.
        start_output = _run_ps_remote_cmd(script_block_start, s.name, s.user, s.password)
        logger.info(f"Triggered start of {s.bat} on {s.name}. Output: {start_output}")
    except Exception as e:
        logger.error(f"Failed to trigger {s.bat} on {s.name}: {e}")
        return None

    sleep(2) # Give some time for the process to start

    # 5. Get PIDs after starting new server
    pids_new = [p['pid'] for p in get_ps_processes(s.name, s.user, s.password, process_name="python")]
    logger.debug(f"Python processes found after: {pids_new}")

    pid = [p for p in pids_new if p not in pids_old]
    print(f"{node_name.upper()} server initiated with pid {pid}")
    logger.info(f"{node_name.upper()} server initiated with pid {pid}")

    if save_pid_txt and pid: # Only save if a new PID was actually found
        with open("server_pids.txt", "a") as f:
            f.write(f"{pid}|{node_name}|{time()}\n")
    return pid