"""Windows Task Scheduler primitives shared by the booth server launcher and deploy.

CTR starts processes on STM/ACQ by creating a scheduled task there and running
it (``SCHTASKS /S /U /P``). ``neurobooth_os.netcomm.client`` uses this to start
the booth servers; ``neurobooth_os.deploy`` uses it to run the deploy agent.

Standard library only (see the package docstring).
"""

import logging
import os
import subprocess
import tempfile
import xml.sax.saxutils as _saxutils
from typing import List, Optional

# Route through the "app" logger so messages reach the PostgreSQLHandler
# attached by make_db_logger (log_manager.py) when running inside a booth
# server. A privately-named logger has no handlers attached there.
logger = logging.getLogger("app")


def run_cmd(cmd_list: List[str], server_name: Optional[str] = None, user: Optional[str] = None,
            password: Optional[str] = None, error_level: int = logging.ERROR,
            timeout: float = 30) -> str:
    """Run a subprocess command and return its stdout.

    Args:
        cmd_list: The command and arguments to run.
        server_name: Remote host for ``/S``. Ignored when ``user`` is empty.
        user: Remote user for ``/U``. An empty user means "run on this machine":
            ``/S /U /P`` are skipped (see docs/single_machine_testing.md).
        password: Remote password for ``/P``.
        error_level: Log level used when the command fails or times out.
            Callers wrapping benign-failure operations (e.g. taskkill where the
            target PID may already be gone) can pass ``logging.WARNING``.
        timeout: Seconds before the command is abandoned.

    Returns:
        The command's stdout.

    Raises:
        subprocess.CalledProcessError: The command exited non-zero.
        subprocess.TimeoutExpired: The command ran longer than ``timeout``.
    """
    full_cmd = list(cmd_list)
    if server_name and user:
        full_cmd = full_cmd[:1] + ["/S", server_name, "/U", user, "/P", password] + full_cmd[1:]

    try:
        logger.debug(f"Running command: {' '.join(cmd_list)} (on {server_name or 'localhost'})")
        result = subprocess.run(full_cmd, capture_output=True, text=True, check=True, timeout=timeout)
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


def build_task_xml(command: str, arguments: Optional[str] = None,
                   user: Optional[str] = None,
                   machine: Optional[str] = None,
                   unqualified_user: bool = False) -> str:
    """Build a Task Scheduler XML for an on-demand task.

    SCHTASKS /Create has no CLI flag for the battery-condition setting, so a
    CLI-created task inherits the Windows default DisallowStartIfOnBatteries=true
    and silently sits in "Queued" on a laptop running on battery (the command
    never launches). /Create /XML lets us write that setting explicitly.

    The trigger keys off Application Event ID 777 — nothing emits that event;
    it exists only so /Run can launch the task on demand.

    When ``user`` is provided, a <Principals> block is included so SCHTASKS
    /S /XML accepts the file: remote task creation requires an explicit
    UserId. The UserId is qualified as ``machine\\user`` unless ``user``
    already contains a backslash or ``unqualified_user`` is set (IP-addressed
    host), in which case the bare ``user`` is used. Local creation (no /S)
    auto-fills Principals, so the block is omitted when ``user`` is empty.

    Args:
        command: Executable or .bat file the task runs.
        arguments: Argument string passed to ``command``, if any.
        user: Account the task runs as (remote creation only).
        machine: Host used to qualify ``user``.
        unqualified_user: Emit ``user`` without the machine prefix.

    Returns:
        The task definition as an XML string.
    """
    command_escaped = _saxutils.escape(command)
    args_block = ""
    if arguments is not None:
        args_block = f"      <Arguments>{_saxutils.escape(arguments)}</Arguments>\n"

    principals_block = ""
    actions_open = "  <Actions>\n"
    if user:
        # Qualify with the target machine name when not already domain-qualified.
        # Bare "ACQ" is rejected by Task Scheduler XML validation as ambiguous;
        # "ACQ\\ACQ" (which is what /Query shows for the existing task) is not.
        if unqualified_user:
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
        f'      <Command>{command_escaped}</Command>\n'
        f'{args_block}'
        '    </Exec>\n'
        '  </Actions>\n'
        '</Task>\n'
    )


def create_task(task_name: str, xml_content: str, server_name: Optional[str] = None,
                user: Optional[str] = None, password: Optional[str] = None) -> None:
    """Create (or overwrite) a scheduled task from an XML definition.

    Args:
        task_name: Task Scheduler name.
        xml_content: Output of :func:`build_task_xml`.
        server_name: Remote host, or None for this machine.
        user: Remote user, or None for this machine.
        password: Remote password.
    """
    fd, xml_path = tempfile.mkstemp(suffix='.xml')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(b'\xff\xfe')  # SCHTASKS /XML expects UTF-16 LE with BOM
            f.write(xml_content.encode('utf-16-le'))
        run_cmd(["SCHTASKS", "/Create", "/TN", task_name, "/XML", xml_path, "/F"],
                server_name, user, password)
    finally:
        try:
            os.remove(xml_path)
        except OSError as e:
            logger.warning(f"Could not remove temporary task XML {xml_path}: {e}")


def run_task(task_name: str, server_name: Optional[str] = None,
             user: Optional[str] = None, password: Optional[str] = None) -> None:
    """Start a scheduled task now (returns without waiting for it to finish)."""
    run_cmd(["SCHTASKS", "/Run", "/TN", task_name], server_name, user, password)


def delete_task(task_name: str, server_name: Optional[str] = None,
                user: Optional[str] = None, password: Optional[str] = None) -> None:
    """Delete a scheduled task."""
    run_cmd(["SCHTASKS", "/Delete", "/TN", task_name, "/F"], server_name, user, password)
