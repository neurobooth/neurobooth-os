"""How the orchestrator runs the agent on a machine.

* :class:`LocalTransport` runs the agent as a subprocess. Used for CTR itself
  in production, and for every simulated machine in the test harness.
* :class:`SchtasksTransport` runs the agent on STM/ACQ through Windows Task
  Scheduler, the same channel CTR already uses to start the booth servers
  (see docs/inter_machine_setup.md). With no host/user it targets this
  machine, which lets the Task Scheduler path be tested on one Windows box.

Both copy this package into ``deploy_runtime/<run_id>/`` on the target first,
so every machine runs the same agent code as the orchestrator regardless of
what is installed there.

Standard library only (see the package docstring).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from neurobooth_os.deploy import schtasks

# Resolved once at import: on CTR this package is loaded through the
# NB_INSTALL link, which a deploy re-points mid-run.
PACKAGE_DIR = Path(os.path.realpath(__file__)).parent
_RUNTIME_KEEP = 5


class TransportError(Exception):
    """The agent could not be run or did not report back."""


@dataclass
class AgentResult:
    ok: bool
    payload: Dict[str, Any]
    log: str
    log_location: str

    @property
    def error(self) -> str:
        return str(self.payload.get("error", ""))


def stage_runtime(destination: Path) -> None:
    """Copy the agent package (standard library only) into ``destination``."""
    package_destination = destination / "neurobooth_os" / "deploy"
    package_destination.mkdir(parents=True, exist_ok=True)
    (destination / "neurobooth_os" / "__init__.py").write_text('"""Neurobooth OS (deploy agent copy)"""\n')
    for source in PACKAGE_DIR.glob("*.py"):
        shutil.copy2(source, package_destination / source.name)


def prune_runtimes(runtime_root: Path, keep: int = _RUNTIME_KEEP) -> None:
    """Delete all but the newest ``keep`` run directories (names sort by time)."""
    if not runtime_root.is_dir():
        return
    runs = sorted(path for path in runtime_root.iterdir() if path.is_dir())
    for stale in runs[:-keep]:
        shutil.rmtree(stale)


class Transport(ABC):
    """Runs agent requests on one machine for one deploy run."""

    def __init__(self, machine: str, run_id: str) -> None:
        self.machine = machine
        self.run_id = run_id
        self._staged = False

    @abstractmethod
    def run(self, request: Dict[str, Any], timeout_s: float) -> AgentResult:
        """Run one agent request and return its result."""

    def close(self) -> None:
        """Release any connection held to the machine."""

    def _read_result(self, result_path: Path, log_path: Path, exit_code: Optional[int]) -> AgentResult:
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        if not result_path.exists():
            raise TransportError(f"{self.machine}: the agent wrote no result (exit code {exit_code}). "
                                 f"Log {log_path}:\n{log_text[-4000:]}")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return AgentResult(ok=bool(payload.get("ok")), payload=payload, log=log_text, log_location=str(log_path))


class LocalTransport(Transport):
    """Run the agent as a subprocess on this machine.

    Args:
        machine: Config name of the machine.
        run_id: Deploy run identifier.
        home: Home directory of the simulated account; None means this
            account's real home (production CTR).
        python: Interpreter for the agent.
    """

    def __init__(self, machine: str, run_id: str, home: Optional[Path] = None,
                 python: str = sys.executable) -> None:
        super().__init__(machine, run_id)
        self.home = home
        self.python = python
        root = (home if home is not None else Path.home()) / "nb_os_env" / "deploy_runtime"
        self.runtime_root = root
        self.runtime = root / run_id

    def run(self, request: Dict[str, Any], timeout_s: float) -> AgentResult:
        if not self._staged:
            stage_runtime(self.runtime)
            prune_runtimes(self.runtime_root)
            self._staged = True
        step = request["command"]
        request = dict(request, home=str(self.home) if self.home is not None else None)
        request_path = self.runtime / f"{step}-request.json"
        result_path = self.runtime / f"{step}-result.json"
        log_path = self.runtime / f"{step}.log"
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
        if result_path.exists():
            result_path.unlink()
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        with open(log_path, "w", encoding="utf-8") as log_file:
            completed = subprocess.run(
                [self.python, "-m", "neurobooth_os.deploy.agent", str(request_path), str(result_path)],
                cwd=str(self.runtime), env=environment, stdout=log_file, stderr=subprocess.STDOUT,
                timeout=timeout_s, check=False,
            )
        return self._read_result(result_path, log_path, completed.returncode)


class SchtasksTransport(Transport):
    """Run the agent on a Windows machine through Task Scheduler.

    The task runs as the booth account (InteractiveToken, so that account must
    be logged in), with that account's environment and git credentials.

    Args:
        machine: Config name of the machine; also its host name.
        run_id: Deploy run identifier.
        user: Booth account on the machine, or None for this machine.
        password: That account's password (from CTR's secrets.yaml).
        remote_home: The account's home as the machine itself sees it.
        share_home: The same directory as CTR reaches it (``\\\\host\\C$\\...``);
            equal to ``remote_home`` when targeting this machine.
        python_command: Command that starts a bare Python on the machine.
        host: Host for ``SCHTASKS /S``; defaults to ``machine``.
        unqualified_user: Passed through to the task XML (IP-addressed hosts).
        home_override: Simulated home sent to the agent (tests only).
        poll_interval_s: Seconds between checks for the agent's result.
    """

    TASK_PREFIX = "neurobooth-deploy"

    def __init__(self, machine: str, run_id: str, user: Optional[str], password: Optional[str],
                 remote_home: str, share_home: Path, python_command: Optional[List[str]] = None,
                 host: Optional[str] = None, unqualified_user: bool = False,
                 home_override: Optional[Path] = None, poll_interval_s: float = 2.0) -> None:
        super().__init__(machine, run_id)
        self.user = user
        self.password = password
        self.host = (host or machine) if user else None
        self.remote_runtime = f"{remote_home}\\nb_os_env\\deploy_runtime\\{run_id}"
        self.share_runtime_root = share_home / "nb_os_env" / "deploy_runtime"
        self.share_runtime = self.share_runtime_root / run_id
        self.python_command = python_command or ["uv", "run", "--no-project", "python"]
        self.unqualified_user = unqualified_user
        self.home_override = home_override
        self.poll_interval_s = poll_interval_s
        # Per machine, so simulated machines sharing one Windows box don't collide.
        self.task_name = f"{self.TASK_PREFIX}-{machine}"

    def _bat(self, step: str) -> str:
        python = " ".join(f'"{part}"' for part in self.python_command)
        return (
            "@echo off\r\n"
            'cd /d "%~dp0"\r\n'
            f'{python} -m neurobooth_os.deploy.agent '
            f'"{step}-request.json" "{step}-result.json" > "{step}.log" 2>&1\r\n'
        )

    @property
    def _share(self) -> str:
        return f"\\\\{self.host}\\C$"

    def _connect_share(self) -> None:
        """Open an SMB session to C$ as the booth account (as the runbook's smoke test does).

        SCHTASKS authenticates per call with /U /P, but copying the agent and
        reading its result go through the share with this session.
        """
        if self.user:
            account = self.user if (self.unqualified_user or "\\" in self.user) else f"{self.host}\\{self.user}"
            schtasks.run_cmd(["net", "use", self._share, self.password or "", f"/USER:{account}"])

    def close(self) -> None:
        if self.user and self._staged:
            schtasks.run_cmd(["net", "use", self._share, "/DELETE", "/Y"])

    def run(self, request: Dict[str, Any], timeout_s: float) -> AgentResult:
        if not self._staged:
            self._connect_share()
            stage_runtime(self.share_runtime)
            prune_runtimes(self.share_runtime_root)
            self._staged = True
        step = request["command"]
        request = dict(request, home=str(self.home_override) if self.home_override is not None else None)
        result_path = self.share_runtime / f"{step}-result.json"
        log_path = self.share_runtime / f"{step}.log"
        (self.share_runtime / f"{step}-request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
        (self.share_runtime / f"{step}.bat").write_text(self._bat(step), encoding="utf-8")
        if result_path.exists():
            result_path.unlink()

        xml = schtasks.build_task_xml(f"{self.remote_runtime}\\{step}.bat", user=self.user,
                                      machine=self.host, unqualified_user=self.unqualified_user)
        schtasks.create_task(self.task_name, xml, self.host, self.user, self.password)
        try:
            schtasks.run_task(self.task_name, self.host, self.user, self.password)
            deadline = time.monotonic() + timeout_s
            while not result_path.exists():
                if time.monotonic() > deadline:
                    raise TransportError(f"{self.machine}: no result after {timeout_s:.0f}s; see {log_path}")
                time.sleep(self.poll_interval_s)
        finally:
            schtasks.delete_task(self.task_name, self.host, self.user, self.password)
        return self._read_result(result_path, log_path, None)
