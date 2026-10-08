"""Deploy, roll back and report on every machine of one environment, from CTR.

A deploy runs in phases, each across all machines before the next starts:

1. **Resolve** the requested refs to commits once, on CTR, so every machine
   gets the identical commit even if a branch moves mid-deploy.
2. **Check** every machine: reachable, nothing running from the install,
   layout sane. Any blocker aborts before anything changes.
3. **Build** the new commits into each machine's inactive slot. Slow (git,
   uv sync) but invisible: the live install is untouched. Any failure aborts
   here, so an environment is never left on mixed versions by a failed build.
4. **Switch** each machine's links to the new slot (seconds); CTR last.

Rollback switches the machines of the most recent deploy back to the slot
they came from — no rebuild, so it also takes seconds.

Unlike the rest of the package this module needs PyYAML and pydantic: it
reads the environment's machines and passwords through neurobooth_os.config.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from neurobooth_os.config import ConfigException, NeuroboothConfig
from neurobooth_os.deploy import gitops
from neurobooth_os.deploy.slots import MachineLayout, other_color, utc_now
from neurobooth_os.deploy.transports import (
    AgentResult,
    LocalTransport,
    SchtasksTransport,
    Transport,
    TransportError,
)

# Environments that may deploy each repo's default branch without naming a
# ref. Everything else is treated as production and needs explicit refs, so
# a new environment is safe by default.
DEFAULT_REF_ENVIRONMENTS = frozenset({"staging"})

STATUS_TIMEOUT_S = 300
BUILD_TIMEOUT_S = 3 * 3600
ACTIVATE_TIMEOUT_S = 300


class DeployError(Exception):
    """The deploy was refused or failed; the message is shown to the operator."""


@dataclass(frozen=True)
class MachineTarget:
    """One machine of the environment and what its venv needs."""

    name: str
    role: str  # "CTR", "STM" or "ACQ"
    user: str
    password: Optional[str]
    unqualified_user: bool = False
    extras: Sequence[str] = ()
    spinnaker_wheel: Optional[str] = None
    labrecorder: bool = False


def machines_from_config(config: NeuroboothConfig) -> List[MachineTarget]:
    """Derive the machines to deploy, and their per-machine steps, from the booth config.

    Roles: the control machine is CTR, the presentation machine is STM, any
    other acquisition machine is ACQ. The EyeLink extra goes where an Eyelink
    device is configured, the Spinnaker wheel where a FLIR device is, and the
    LabRecorder swap on CTR.

    Raises:
        ConfigException: A FLIR machine has no ``spinnaker_wheel`` configured.
    """
    services = [config.control, config.presentation] + list(config.acquisition)
    devices: Dict[str, List[str]] = {name: [] for name in config.machines}
    for service in services:
        devices[service.name].extend(service.devices)

    targets = []
    for name, machine in config.machines.items():
        if name == config.control.name:
            role = "CTR"
        elif name == config.presentation.name:
            role = "STM"
        else:
            role = "ACQ"
        machine_devices = devices[name]
        wheel = None
        if any(device.startswith("FLIR") for device in machine_devices):
            if not machine.spinnaker_wheel:
                raise ConfigException(
                    f"Machine '{name}' has FLIR devices but no machines.{name}.spinnaker_wheel in the config. "
                    f"Set it to the Spinnaker wheel's path on that machine."
                )
            wheel = machine.spinnaker_wheel
        targets.append(MachineTarget(
            name=name, role=role, user=machine.user,
            password=machine.password.get_secret_value() if machine.password else None,
            unqualified_user=machine.unqualified_user,
            extras=("eyelink",) if any(device.startswith("Eyelink") for device in machine_devices) else (),
            spinnaker_wheel=wheel,
            labrecorder=(role == "CTR"),
        ))
    # CTR last: it switches after the machines it drives.
    return sorted(targets, key=lambda target: target.role == "CTR")


def booth_transport_factory(target: MachineTarget, run_id: str) -> Transport:
    """Production transports: CTR runs the agent locally, STM/ACQ via Task Scheduler."""
    if target.role == "CTR":
        return LocalTransport(target.name, run_id)
    if target.password is None:
        raise ConfigException(f"No password for machine '{target.name}' in CTR's secrets.yaml")
    return SchtasksTransport(
        target.name, run_id, user=target.user, password=target.password,
        remote_home=f"C:\\Users\\{target.user}",
        share_home=Path(f"\\\\{target.name}\\C$\\Users\\{target.user}"),
        unqualified_user=target.unqualified_user,
    )


TransportFactory = Callable[[MachineTarget, str], Transport]


@dataclass
class Outcome:
    """What happened on one machine in one phase."""

    machine: str
    ok: bool
    error: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    log_location: str = ""


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


class Orchestrator:
    """Runs deploy/rollback/status for one environment.

    Args:
        environment: Folder name under the configs repo's ``environments/``.
        targets: Machines, from :func:`machines_from_config`.
        ctr_layout: CTR's own layout; its repos resolve refs and its slots
            directory holds the deploy history.
        transport_factory: Builds the transport for each machine.
        uv: Command that runs uv on the machines.
        output: Where progress lines go.
    """

    def __init__(self, environment: str, targets: List[MachineTarget], ctr_layout: MachineLayout,
                 transport_factory: TransportFactory = booth_transport_factory,
                 uv: Optional[List[str]] = None, output: Callable[[str], None] = print) -> None:
        self.environment = environment
        self.targets = targets
        self.ctr_layout = ctr_layout
        self.transport_factory = transport_factory
        self.uv = uv or ["uv"]
        self.output = output
        self.history_file = ctr_layout.slots_root / "history.jsonl"

    # -- plumbing ------------------------------------------------------------

    def _run_all(self, transports: Dict[str, Transport], requests: Dict[str, Dict[str, Any]],
                 timeout_s: float) -> Dict[str, Outcome]:
        def run_one(name: str) -> Outcome:
            try:
                result: AgentResult = transports[name].run(requests[name], timeout_s)
            except (TransportError, OSError) as error:
                return Outcome(name, False, error=str(error))
            except Exception as error:  # noqa: BLE001 - e.g. SCHTASKS failing; reported against the machine
                return Outcome(name, False, error=f"{type(error).__name__}: {error}")
            return Outcome(name, result.ok, error=result.error, payload=result.payload,
                           log_location=result.log_location)

        if not requests:
            return {}
        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            return dict(zip(requests, pool.map(run_one, list(requests))))

    def _transports(self, run_id: str) -> Dict[str, Transport]:
        return {target.name: self.transport_factory(target, run_id) for target in self.targets}

    @staticmethod
    def _close(transports: Dict[str, Transport]) -> None:
        for transport in transports.values():
            transport.close()

    def _report_failures(self, phase: str, outcomes: Dict[str, Outcome]) -> bool:
        failed = [outcome for outcome in outcomes.values() if not outcome.ok]
        for outcome in failed:
            location = f" (log: {outcome.log_location})" if outcome.log_location else ""
            self.output(f"  {outcome.machine}: {phase} FAILED: {outcome.error}{location}")
        return bool(failed)

    def _check(self, transports: Dict[str, Transport], run_id: str, names: Sequence[str]) -> Dict[str, Outcome]:
        """Status of ``names``; raises DeployError if any is unreachable or blocked."""
        outcomes = self._run_all(transports, {name: {"command": "status", "run_id": run_id} for name in names},
                                 STATUS_TIMEOUT_S)
        if self._report_failures("check", outcomes):
            raise DeployError("Could not check every machine; nothing was changed.")
        blocked = False
        for name, outcome in outcomes.items():
            status = outcome.payload["status"]
            for command_line in status["running"]:
                self.output(f"  {name}: running from the install: {command_line}")
                blocked = True
            for problem in status["problems"]:
                self.output(f"  {name}: {problem}")
                blocked = True
        if blocked:
            raise DeployError("Blocked (see above); nothing was changed. Stop booth processes and fix the "
                              "problems listed, then rerun.")
        return outcomes

    def _append_history(self, entry: Dict[str, Any]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "a", encoding="utf-8") as history:
            history.write(json.dumps(entry) + "\n")

    def last_history_entry(self) -> Optional[Dict[str, Any]]:
        if not self.history_file.exists():
            return None
        lines = [line for line in self.history_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        return json.loads(lines[-1]) if lines else None

    def _switch(self, transports: Dict[str, Transport], run_id: str,
                colors: Dict[str, str], expect: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Outcome]:
        """Activate ``colors[name]`` on each machine; CTR after the others."""
        def request(name: str) -> Dict[str, Any]:
            return {"command": "activate", "run_id": run_id, "color": colors[name],
                    "expect": (expect or {}).get(name, {})}

        ctr = [t.name for t in self.targets if t.role == "CTR" and t.name in colors]
        others = [name for name in colors if name not in ctr]
        outcomes = self._run_all(transports, {name: request(name) for name in others}, ACTIVATE_TIMEOUT_S)
        if ctr and all(outcome.ok for outcome in outcomes.values()):
            outcomes.update(self._run_all(transports, {name: request(name) for name in ctr}, ACTIVATE_TIMEOUT_S))
        return outcomes

    # -- commands ------------------------------------------------------------

    def resolve(self, os_ref: Optional[str], config_ref: Optional[str]) -> Dict[str, gitops.ResolvedRef]:
        """Pin the requested refs to commits; default branches only where allowed."""
        if (os_ref is None or config_ref is None) and self.environment not in DEFAULT_REF_ENVIRONMENTS:
            raise DeployError(
                f"'{self.environment}' is a production environment: name both refs explicitly, e.g. "
                f"nb_deploy --os-ref v1.2.3 --config-ref v1.2.3"
            )
        resolved = {}
        for key, repo, ref in (("os", self.ctr_layout.install_link, os_ref),
                               ("config", self.ctr_layout.configs_repo, config_ref)):
            resolved[key] = gitops.resolve_remote_ref(repo, ref or gitops.default_branch(repo))
        return resolved

    def deploy(self, os_ref: Optional[str] = None, config_ref: Optional[str] = None,
               dry_run: bool = False) -> int:
        """Bring every machine to the requested commits. Returns a process exit code."""
        run_id = new_run_id()
        targets = self.resolve(os_ref, config_ref)
        self.output(f"Deploy {run_id} to '{self.environment}': neurobooth-os {targets['os'].label}, "
                    f"configs {targets['config'].label}")
        transports = self._transports(run_id)
        try:
            self.output("Checking machines...")
            statuses = self._check(transports, run_id, [t.name for t in self.targets])

            pending = []
            for target in self.targets:
                current = statuses[target.name].payload["status"]["current"]
                up_to_date = (current.get("os_sha") == targets["os"].sha
                              and current.get("config_sha") == targets["config"].sha
                              and current.get("environment") in ("", self.environment))
                state = "up to date" if up_to_date else (
                    f"{current.get('os_ref', '?')} {current.get('os_sha', '')[:7]} -> {targets['os'].label}")
                self.output(f"  {target.name} ({target.role}): {state}")
                if not up_to_date:
                    pending.append(target)
            if not pending:
                self.output("Nothing to deploy: every machine is already up to date.")
                return 0
            if dry_run:
                self.output(f"Dry run: would deploy to {', '.join(t.name for t in pending)}.")
                return 0

            self.output(f"Building on {', '.join(t.name for t in pending)} (the live install is not touched)...")
            build_requests = {
                target.name: {
                    "command": "build", "run_id": run_id, "environment": self.environment,
                    "os": {"ref": targets["os"].ref, "sha": targets["os"].sha, "label": targets["os"].label},
                    "config": {"ref": targets["config"].ref, "sha": targets["config"].sha,
                               "label": targets["config"].label},
                    "extras": list(target.extras), "spinnaker_wheel": target.spinnaker_wheel,
                    "labrecorder": target.labrecorder, "uv": self.uv,
                }
                for target in pending
            }
            built = self._run_all(transports, build_requests, BUILD_TIMEOUT_S)
            if self._report_failures("build", built):
                self.output("Nothing was switched: every machine is still running its previous version.")
                return 1

            colors = {name: outcome.payload["color"] for name, outcome in built.items()}
            previous = {name: statuses[name].payload["status"]["active"] or other_color(colors[name])
                        for name in colors}
            self.output("Switching...")
            switched = self._switch(transports, run_id, colors, expect={
                name: {"os_sha": targets["os"].sha, "config_sha": targets["config"].sha} for name in colors})
            done = {name: {"from": previous[name], "to": colors[name]}
                    for name, outcome in switched.items() if outcome.ok}
            if done:
                self._append_history({"run_id": run_id, "kind": "deploy", "at": utc_now(),
                                      "environment": self.environment, "os": targets["os"].label,
                                      "config": targets["config"].label, "switched": done})
            if self._report_failures("switch", switched) or len(done) != len(colors):
                self.output("Not every machine switched. Run `nb_deploy rollback` to put the switched "
                            "machines back, or fix the failure and rerun the deploy.")
                return 1
            self.output(f"Deployed neurobooth-os {targets['os'].label} + configs {targets['config'].label} "
                        f"to {', '.join(done)}. Undo with `nb_deploy rollback`.")
            return 0
        finally:
            self._close(transports)

    def rollback(self, dry_run: bool = False) -> int:
        """Switch the machines of the most recent deploy (or rollback) back. Returns an exit code."""
        last = self.last_history_entry()
        if last is None:
            raise DeployError(f"Nothing to roll back: no deploy history in {self.history_file}")
        known = {target.name for target in self.targets}
        unknown = set(last["switched"]) - known
        if unknown:
            raise DeployError(f"The last deploy switched machines no longer in the config: {sorted(unknown)}")
        run_id = new_run_id()
        colors = {name: change["from"] for name, change in last["switched"].items()}
        self.output(f"Rollback {run_id}: undoing {last['kind']} {last['run_id']} on {', '.join(colors)}")
        transports = self._transports(run_id)
        try:
            statuses = self._check(transports, run_id, list(colors))
            for name, color in colors.items():
                status = statuses[name].payload["status"]
                record = status["slots"].get(color)
                if status["active"] != last["switched"][name]["to"]:
                    raise DeployError(f"{name} is on the {status['active']} slot, not the {last['switched'][name]['to']} "
                                      f"slot that {last['run_id']} activated; nothing was changed.")
                if record is None or record["status"] != "ready":
                    raise DeployError(f"{name}: the {color} slot is not ready; nothing was changed.")
                self.output(f"  {name}: {status['active']} -> {color} "
                            f"(neurobooth-os {record['os_ref']} {record['os_sha'][:7]})")
            if dry_run:
                self.output("Dry run: nothing was changed.")
                return 0
            switched = self._switch(transports, run_id, colors)
            done = {name: {"from": last["switched"][name]["to"], "to": colors[name]}
                    for name, outcome in switched.items() if outcome.ok}
            if done:
                self._append_history({"run_id": run_id, "kind": "rollback", "undoes": last["run_id"],
                                      "at": utc_now(), "environment": self.environment, "switched": done})
            if self._report_failures("switch", switched) or len(done) != len(colors):
                return 1
            self.output("Rolled back. Running `nb_deploy rollback` again re-applies it.")
            return 0
        finally:
            self._close(transports)

    def status(self) -> int:
        """Print each machine's active and standby slot. Returns an exit code."""
        run_id = new_run_id()
        transports = self._transports(run_id)
        try:
            outcomes = self._run_all(
                transports, {t.name: {"command": "status", "run_id": run_id} for t in self.targets},
                STATUS_TIMEOUT_S)
        finally:
            self._close(transports)
        failed = self._report_failures("status", outcomes)
        for target in self.targets:
            outcome = outcomes[target.name]
            if not outcome.ok:
                continue
            status = outcome.payload["status"]
            self.output(f"{target.name} ({target.role}) — layout: {status['layout']}, active: {status['active']}")
            for color, record in sorted(status["slots"].items()):
                marker = "*" if color == status["active"] else " "
                self.output(f"  {marker} {color:5} {record['status']:8} neurobooth-os {record['os_ref']} "
                            f"{record['os_sha'][:7]}  configs {record['config_ref']} {record['config_sha'][:7]}")
            for line in status["running"]:
                self.output(f"    running: {line}")
            for problem in status["problems"]:
                self.output(f"    problem: {problem}")
        return 1 if failed else 0
