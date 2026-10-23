"""Deploy a release to every machine of a booth environment, from any one of them.

Called by the ``deploy_all.bat`` at the root of each repo:

    neurobooth-os:  deploy_all.bat v1.2.3          runs github_checkout.bat v1.2.3
    configs:        deploy_all.bat v1.2.3 staging  runs checkout_and_deploy.bat v1.2.3 staging

Each other machine runs that repo's per-machine script through Windows Task
Scheduler, the same channel CTR uses to start the STM and ACQ servers (see
docs/inter_machine_setup.md). This machine deploys last. Stops at the first
failure.

The machine list and passwords come from neurobooth_os_config.yaml and the
secrets.yaml beside it: for configs, the environment's folder in the configs
repo; for neurobooth-os, %NB_CONFIG%. The machine you run it from needs
``machines.<name>.password`` for every other machine.
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from neurobooth_os import config
from neurobooth_os.config import MachineSpec
from neurobooth_os.netcomm.client import _build_task_xml, _run_cmd

TASK_NAME = "nb_deploy_all"
LOG_NAME = "deploy_all.log"
TASK_NEVER_RAN = "267011"  # SCHTASKS "Last Result" before the first run
TASK_STILL_RUNNING = "267009"
TIMEOUT_SECONDS = 600
POLL_SECONDS = 3


@dataclass
class DeployPlan:
    """What to run on each machine, and where to find the machine list."""

    repo_dir: Path
    script_args: List[str]  # per-machine script and its arguments
    config_path: Path

    @property
    def command(self) -> List[str]:
        r"""The script and arguments, with the script called as .\script.bat.

        The explicit .\ runs it from the repo folder even where cmd.exe is set
        not to search the current folder (NoDefaultCurrentDirectoryInExePath).
        """
        return [f".\\{self.script_args[0]}", *self.script_args[1:]]

    @property
    def ref(self) -> str:
        """The tag (or other git ref) being deployed: both scripts take it first."""
        return self.script_args[1]


def check_ref_exists(plan: DeployPlan) -> None:
    """Fetch here and fail before touching any machine if the ref doesn't exist.

    Raises:
        RuntimeError: The fetch failed, or the ref is not in the repo after it.
    """
    fetch = subprocess.run(["git", "fetch", "--tags", "--force"], cwd=plan.repo_dir,
                           capture_output=True, text=True)
    if fetch.returncode != 0:
        raise RuntimeError(f"git fetch failed in {plan.repo_dir}:\n{fetch.stderr}")
    lookup = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{plan.ref}^{{commit}}"],
                            cwd=plan.repo_dir, capture_output=True, text=True)
    if lookup.returncode != 0:
        raise RuntimeError(f"'{plan.ref}' is not a tag or branch in {plan.repo_dir} "
                           f"(after git fetch). No machine was changed.")


def is_this_machine(machine: MachineSpec) -> bool:
    """True if ``machine`` is the account this script runs as.

    Matched by user, not host name: staging and Merrimac share the same
    physical machines under different accounts. An empty user means a
    single-machine environment.
    """
    return machine.user == "" or machine.user.upper() == os.environ["USERNAME"].upper()


def remote_repo_dir(repo_dir: Path, user: str) -> Path:
    """Where the repo is on another machine: same place under that user's home."""
    return Path("C:/Users", user) / repo_dir.relative_to(Path.home())


def deploy_remote(host: str, machine: MachineSpec, plan: DeployPlan) -> None:
    """Run the per-machine script on ``host`` and wait for it to finish.

    Raises:
        RuntimeError: The deploy failed, or never started within the timeout.
    """
    if machine.password is None:
        raise RuntimeError(
            f"No password for '{host}' in the secrets.yaml next to {plan.config_path} "
            f"(machines.{host}.password)."
        )
    password = machine.password.get_secret_value()
    remote_dir = remote_repo_dir(plan.repo_dir, machine.user)
    arguments = (
        f'/c cd /d "{remote_dir}" && {" ".join(plan.command)} > {LOG_NAME} 2>&1'
    )
    task_xml = _build_task_xml(
        "cmd.exe",
        arguments,  # becomes the task's <Arguments>
        user=machine.user,
        machine=host,
        unqualified_user=machine.unqualified_user,
    )

    file_descriptor, xml_path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(file_descriptor, "wb") as xml_file:
            xml_file.write(b"\xff\xfe")  # SCHTASKS /XML expects UTF-16 LE with BOM
            xml_file.write(task_xml.encode("utf-16-le"))
        _run_cmd(["SCHTASKS", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
                 host, machine.user, password)
    finally:
        os.remove(xml_path)
    _run_cmd(["SCHTASKS", "/Run", "/TN", TASK_NAME], host, machine.user, password)

    log_path = remote_dir / LOG_NAME
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        query_output = _run_cmd(["SCHTASKS", "/Query", "/TN", TASK_NAME, "/V", "/FO", "CSV"],
                                host, machine.user, password)
        task_row = next(csv.DictReader(io.StringIO(query_output)))
        last_result = task_row["Last Result"]
        if task_row["Status"] == "Running" or last_result in (TASK_NEVER_RAN, TASK_STILL_RUNNING):
            continue
        if last_result != "0":
            raise RuntimeError(f"Deploy on '{host}' failed (exit code {last_result}). "
                               f"See {log_path} on that machine.")
        return
    raise RuntimeError(
        f"Deploy on '{host}' did not finish within {TIMEOUT_SECONDS}s. The task only "
        f"runs while {machine.user} is logged in on {host}. See {log_path} on that machine."
    )


def deploy_local(plan: DeployPlan) -> None:
    """Run the per-machine script here, with its output shown in this window."""
    result = subprocess.run(["cmd", "/c", *plan.command], cwd=plan.repo_dir)
    if result.returncode != 0:
        raise RuntimeError(f"Deploy on this machine failed (exit code {result.returncode}).")


def deploy_everywhere(plan: DeployPlan) -> int:
    """Deploy to the other machines of the environment, then this one.

    Returns:
        0 if every machine deployed, 1 otherwise.
    """
    config.load_neurobooth_config(str(plan.config_path))
    machines: Dict[str, MachineSpec] = config.neurobooth_config.machines

    local_hosts = [host for host, machine in machines.items() if is_this_machine(machine)]
    if len(local_hosts) != 1:
        print(f"Could not tell which machine this is: user {os.environ['USERNAME']} "
              f"matches {local_hosts or 'none'} of {list(machines)}.")
        return 1
    remote_hosts = [host for host in machines if host not in local_hosts]

    finished: List[str] = []
    for host in remote_hosts + local_hosts:
        print(f"\n=== {' '.join(plan.script_args)} on {host} ===", flush=True)
        try:
            if host in remote_hosts:
                deploy_remote(host, machines[host], plan)
            else:
                deploy_local(plan)
        except (RuntimeError, subprocess.CalledProcessError) as error:
            print(f"\nFAILED on {host}: {error}")
            if isinstance(error, subprocess.CalledProcessError):
                print(error.stderr)
            not_started = [other for other in remote_hosts + local_hosts
                           if other != host and other not in finished]
            print(f"Deployed: {finished or 'none'}. Not started: {not_started or 'none'}.")
            return 1
        finished.append(host)
        print(f"{host}: OK", flush=True)

    print(f"\nDeployed to {', '.join(finished)}.")
    return 0


def plan_from_args(arguments: List[str]) -> DeployPlan:
    """Build a plan from ``<neurobooth-os|configs> <repo_dir> TAG [env_name]``.

    Raises:
        ValueError: The arguments are wrong; the message says how to call it.
    """
    usage = ("Usage: deploy_all.bat TAG             (in the neurobooth-os repo)\n"
             "       deploy_all.bat TAG env_name    (in the configs repo)")
    if len(arguments) < 2:
        raise ValueError(usage)
    repo_kind, repo_dir, tag_and_env = arguments[0], Path(arguments[1]).resolve(), arguments[2:]

    if repo_kind == "neurobooth-os" and len(tag_and_env) == 1:
        config_dir = os.environ.get("NB_CONFIG")
        if config_dir is None:
            raise ValueError("NB_CONFIG is not set. Deploy the configs on this machine first.")
        return DeployPlan(repo_dir, ["github_checkout.bat", tag_and_env[0]],
                          Path(config_dir) / "neurobooth_os_config.yaml")

    if repo_kind == "configs" and len(tag_and_env) == 2:
        tag, env_name = tag_and_env
        environments_dir = repo_dir / "environments"
        if not (environments_dir / env_name).is_dir():
            valid_names = sorted(path.name for path in environments_dir.iterdir() if path.is_dir())
            raise ValueError(f"'{env_name}' is not an environment. "
                             f"Valid names: {', '.join(valid_names)}")
        return DeployPlan(repo_dir, ["checkout_and_deploy.bat", tag, env_name],
                          environments_dir / env_name / "neurobooth_os_config.yaml")

    raise ValueError(usage)


def main() -> int:
    try:
        plan = plan_from_args(sys.argv[1:])
        check_ref_exists(plan)
    except (ValueError, RuntimeError) as error:
        print(error)
        return 1
    return deploy_everywhere(plan)


if __name__ == "__main__":
    sys.exit(main())
