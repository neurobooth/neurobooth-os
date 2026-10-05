"""Per-machine deploy agent.

The orchestrator on CTR copies this package to each machine and runs::

    python -m neurobooth_os.deploy.agent REQUEST.json RESULT.json

``REQUEST.json`` names one command:

* ``status``   — report the slots, what is active, and anything blocking a deploy.
* ``build``    — build the requested commits into the inactive slot (adopting a
  pre-blue-green install into the ``blue`` slot on first use).
* ``activate`` — point ``NB_INSTALL``/``NB_CONFIG`` at a built slot.

``RESULT.json`` is always written, including on failure, and the exit code is
0 only on success. Progress goes to stdout, which the orchestrator captures
as the machine's deploy log.

Standard library only (see the package docstring).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from neurobooth_os.deploy import gitops
from neurobooth_os.deploy.processes import find_install_processes
from neurobooth_os.deploy.slots import (
    BUILDING,
    FAILED,
    READY,
    MachineLayout,
    MachineState,
    SlotError,
    SlotRecord,
    is_link,
    other_color,
    point_link,
    remove_slot_tree,
    replace_file,
    same_path,
    utc_now,
)

RELEASE_FILE = Path("neurobooth_os") / "current_release.py"
CONFIG_VERSION_FILE = Path("neurobooth_os") / "current_config.py"
LABRECORDER_SCRIPT = Path("extras") / "perf" / "upgrade_labrecorder_v1.17.1.ps1"
ADOPTED_REF = "pre-blue-green install"


class AgentError(Exception):
    """A deploy step failed or was refused; the message is shown to the operator."""


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def layout_kind(layout: MachineLayout) -> str:
    """``slots`` (blue-green), ``legacy`` (plain checkout at NB_INSTALL) or ``empty``."""
    if is_link(layout.install_link):
        return "slots"
    if layout.install_link.is_dir():
        return "legacy"
    return "empty"


def environment_problems(layout: MachineLayout) -> List[str]:
    """Mismatches between the booth's NB_INSTALL/NB_CONFIG and the slot layout."""
    problems = []
    for variable, expected in (("NB_INSTALL", layout.install_link), ("NB_CONFIG", layout.config_link)):
        value = os.environ.get(variable)
        if not value:
            problems.append(f"{variable} is not set (expected {expected})")
        elif os.path.normcase(os.path.normpath(value)) != os.path.normcase(os.path.normpath(str(expected))):
            problems.append(f"{variable} is {value}, but the deploy layout expects {expected}")
    return problems


def blocking_processes(layout: MachineLayout) -> List[str]:
    return [p.command_line for p in find_install_processes([layout.install_link, layout.slots_root])]


def status(layout: MachineLayout, check_environment: bool) -> Dict[str, Any]:
    kind = layout_kind(layout)
    state = MachineState.load(layout)
    problems = environment_problems(layout) if check_environment else []
    current: Dict[str, str] = {}
    if kind == "slots":
        if state.active is None or state.active not in state.slots:
            problems.append(f"{layout.install_link} is a link but {layout.state_file} has no active slot")
        else:
            record = state.slots[state.active]
            current = {"os_ref": record.os_ref, "os_sha": record.os_sha,
                       "config_ref": record.config_ref, "config_sha": record.config_sha,
                       "environment": record.environment}
            for link, slot_path in ((layout.install_link, layout.slot_install(state.active)),
                                    (layout.config_link, layout.slot_config(state.active))):
                if not same_path(link, slot_path):
                    problems.append(f"{link} does not point at the active slot {slot_path}")
    elif kind == "legacy":
        current = {"os_ref": ADOPTED_REF, "os_sha": gitops.head_sha(layout.install_link),
                   "config_ref": ADOPTED_REF,
                   "config_sha": gitops.head_sha(layout.configs_repo) if (layout.configs_repo / ".git").exists() else "",
                   "environment": ""}
    configs_dirty = (layout.configs_repo / ".git").exists() and gitops.has_tracked_changes(layout.configs_repo)
    if configs_dirty:
        problems.append(f"{layout.configs_repo} has uncommitted changes to tracked files")
    return {
        "layout": kind,
        "active": state.active,
        "previous_active": state.previous_active,
        "activated_by_run": state.activated_by_run,
        "current": current,
        "slots": {color: asdict(record) for color, record in state.slots.items()},
        "running": blocking_processes(layout),
        "problems": problems,
    }


def require_deployable(layout: MachineLayout, check_environment: bool) -> None:
    """Raise unless nothing is running from the install and the layout is sane."""
    running = blocking_processes(layout)
    if running:
        raise AgentError("Booth processes are running from the install; stop them first:\n  "
                         + "\n  ".join(running))
    if check_environment:
        problems = environment_problems(layout)
        if problems:
            raise AgentError("; ".join(problems))


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def adopt_legacy_install(layout: MachineLayout, state: MachineState) -> None:
    """Move a plain checkout at NB_INSTALL (and its NB_CONFIG) into the blue slot.

    The moved venv still refers to the old NB_INSTALL path, which from now on
    is the link. That resolves to blue exactly when blue is active, so the
    adopted slot keeps working as a rollback target; it is rebuilt from scratch
    the first time it becomes a build target again.
    """
    blue = "blue"
    if layout.slot_dir(blue).exists():
        raise AgentError(f"Cannot adopt the existing install: {layout.slot_dir(blue)} already exists. "
                         f"A previous adoption was interrupted; see docs/deployment.md (Recovery).")
    if not layout.config_link.is_dir() or is_link(layout.config_link):
        raise AgentError(f"Cannot adopt the existing install: {layout.config_link} is missing")
    os_sha = gitops.head_sha(layout.install_link)
    config_sha = gitops.head_sha(layout.configs_repo) if (layout.configs_repo / ".git").exists() else ""

    log(f"Adopting the existing install at {layout.install_link} as the blue slot")
    layout.slot_dir(blue).mkdir(parents=True)
    try:
        os.rename(layout.install_link, layout.slot_install(blue))
    except OSError as error:
        layout.slot_dir(blue).rmdir()
        raise AgentError(f"Could not move {layout.install_link} into the blue slot ({error}). Close any "
                         f"terminal, Explorer window or editor open inside it and retry.") from error
    try:
        os.rename(layout.config_link, layout.slot_config(blue))
    except OSError as error:
        os.rename(layout.slot_install(blue), layout.install_link)
        layout.slot_dir(blue).rmdir()
        raise AgentError(f"Could not move {layout.config_link} into the blue slot ({error}). Close anything "
                         f"open inside it and retry.") from error
    point_link(layout.install_link, layout.slot_install(blue))
    point_link(layout.config_link, layout.slot_config(blue))

    state.active = blue
    state.activated_at = utc_now()
    state.slots[blue] = SlotRecord(
        color=blue, status=READY, os_ref=ADOPTED_REF, os_sha=os_sha,
        config_ref=ADOPTED_REF, config_sha=config_sha, built_at=utc_now(), adopted=True,
    )
    state.save(layout)


def run_step(description: str, command: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> None:
    log(f"{description}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=str(cwd), env=env, check=False)
    if completed.returncode != 0:
        raise AgentError(f"{description} failed with exit code {completed.returncode}")


def prepare_os_checkout(layout: MachineLayout, source_color: str, target_color: str, sha: str) -> Path:
    """Check ``sha`` out in the target slot, cloning from the active slot if needed."""
    source = layout.slot_install(source_color)
    destination = layout.slot_install(target_color)
    url = gitops.origin_url(source)
    if not (destination / ".git").exists():
        remove_slot_tree(layout, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        log(f"Cloning {source} into {destination}")
        gitops.git(layout.slots_root, "clone", "--no-checkout", str(source), str(destination))
    gitops.git(destination, "remote", "set-url", "origin", url)
    log(f"Fetching neurobooth-os in the {target_color} slot")
    gitops.fetch(destination)
    if not gitops.has_commit(destination, sha):
        raise AgentError(f"neurobooth-os commit {sha} is not on origin ({url})")
    gitops.checkout_detached(destination, sha)
    return destination


def materialize_config(layout: MachineLayout, target_color: str, sha: str, environment: str) -> None:
    """Check out the configs commit and copy shared/ + environments/<env>/ into the slot.

    Same result as configs/deploy.bat, but into the inactive slot instead of
    over the live NB_CONFIG.
    """
    repo = layout.configs_repo
    if not (repo / ".git").exists():
        raise AgentError(f"No configs checkout at {repo}")
    if gitops.has_tracked_changes(repo):
        raise AgentError(f"{repo} has uncommitted changes to tracked files")
    log("Fetching configs")
    gitops.fetch(repo)
    if not gitops.has_commit(repo, sha):
        raise AgentError(f"configs commit {sha} is not on origin")
    gitops.checkout_detached(repo, sha)
    environment_dir = repo / "environments" / environment
    if not environment_dir.is_dir():
        raise AgentError(f"'{environment}' is not a directory in {repo / 'environments'}")
    destination = layout.slot_config(target_color)
    remove_slot_tree(layout, destination)
    shutil.copytree(repo / "shared", destination)
    shutil.copytree(environment_dir, destination, dirs_exist_ok=True)
    log(f"Config for '{environment}' written to {destination}")


def write_version_file(path: Path, description: str, label: str) -> None:
    """Write a version stamp in the same format the configs .bat scripts produce."""
    path.write_text(
        f'\n\n"""\n    Stores neurobooth {description}.\n    GENERATED FILE. DO NOT EDIT MANUALLY\n"""\n\n'
        f"version = '{label}'\n",
        encoding="utf-8",
    )


def venv_python(slot_install: Path) -> Path:
    if sys.platform == "win32":
        return slot_install / ".venv" / "Scripts" / "python.exe"
    return slot_install / ".venv" / "bin" / "python"


def build_venv(layout: MachineLayout, slot_install: Path, rebuild: bool, request: Dict[str, Any]) -> None:
    """Sync the slot's venv and apply this machine's post-sync steps."""
    if rebuild:
        log("Removing the venv carried over from the pre-blue-green install")
        remove_slot_tree(layout, slot_install / ".venv")
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    # Post-sync scripts locate the venv through NB_INSTALL; point it at the
    # slot being built, not the live link.
    environment["NB_INSTALL"] = str(slot_install)
    uv = list(request["uv"])
    extras = [f"--extra={extra}" for extra in request.get("extras", [])]
    run_step("uv sync", uv + ["sync", "--locked"] + extras, slot_install, environment)
    wheel = request.get("spinnaker_wheel")
    if wheel:
        run_step("Install Spinnaker wheel",
                 uv + ["pip", "install", "--python", str(venv_python(slot_install)), wheel],
                 slot_install, environment)
    if request.get("labrecorder"):
        script = slot_install / LABRECORDER_SCRIPT
        if script.exists():
            if sys.platform != "win32":
                raise AgentError(f"{LABRECORDER_SCRIPT} only runs on Windows")
            run_step("LabRecorder swap",
                     ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                     slot_install, environment)
        else:
            log(f"{LABRECORDER_SCRIPT} is not in this commit; skipping the LabRecorder swap")


def build(layout: MachineLayout, request: Dict[str, Any], check_environment: bool) -> Dict[str, Any]:
    require_deployable(layout, check_environment)
    kind = layout_kind(layout)
    if kind == "empty":
        raise AgentError(f"No install at {layout.install_link}. Set the machine up by hand first "
                         f"(README.md) and then deploy.")
    state = MachineState.load(layout)
    if kind == "legacy":
        adopt_legacy_install(layout, state)
    if state.active is None:
        raise AgentError(f"{layout.state_file} has no active slot")

    source, target = state.active, other_color(state.active)
    rebuild_venv = target in state.slots and state.slots[target].adopted
    os_target, config_target = request["os"], request["config"]
    record = SlotRecord(
        color=target, status=BUILDING, os_ref=os_target["ref"], os_sha=os_target["sha"],
        config_ref=config_target["ref"], config_sha=config_target["sha"],
        environment=request["environment"], run_id=request["run_id"],
    )
    state.slots[target] = record
    state.save(layout)
    log(f"Building {os_target['label']} + config {config_target['label']} into the {target} slot "
        f"(active: {source})")
    try:
        slot_install = prepare_os_checkout(layout, source, target, os_target["sha"])
        materialize_config(layout, target, config_target["sha"], request["environment"])
        write_version_file(slot_install / RELEASE_FILE, "version number", os_target["label"])
        write_version_file(slot_install / CONFIG_VERSION_FILE, "config version number", config_target["label"])
        build_venv(layout, slot_install, rebuild_venv, request)
    except BaseException:
        record.status = FAILED
        state.save(layout)
        raise
    record.status = READY
    record.built_at = utc_now()
    state.save(layout)
    log(f"The {target} slot is ready")
    return {"color": target, "record": asdict(record)}


# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------

def activate(layout: MachineLayout, request: Dict[str, Any], check_environment: bool) -> Dict[str, Any]:
    require_deployable(layout, check_environment)
    state = MachineState.load(layout)
    color = request["color"]
    record = state.slots.get(color)
    if record is None or record.status != READY:
        raise AgentError(f"The {color} slot is not ready to activate "
                         f"(status: {record.status if record else 'never built'})")
    for key in ("os_sha", "config_sha"):
        expected = request.get("expect", {}).get(key)
        if expected and getattr(record, key) != expected:
            raise AgentError(f"The {color} slot has {key}={getattr(record, key)}, expected {expected}")
    if state.active == color:
        log(f"The {color} slot is already active")
        return {"color": color, "changed": False}

    previous = state.active
    point_link(layout.install_link, layout.slot_install(color))
    try:
        point_link(layout.config_link, layout.slot_config(color))
    except BaseException:
        if previous is not None:
            point_link(layout.install_link, layout.slot_install(previous))
        raise
    state.previous_active = previous
    state.active = color
    state.activated_by_run = request["run_id"]
    state.activated_at = utc_now()
    state.save(layout)
    log(f"Switched from {previous} to {color}")
    return {"color": color, "previous": previous, "changed": True}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

COMMANDS = {"status", "build", "activate"}


def handle(request: Dict[str, Any]) -> Dict[str, Any]:
    """Run one request and return its result payload."""
    command = request["command"]
    if command not in COMMANDS:
        raise AgentError(f"Unknown command '{command}'")
    # An explicit home is only passed by the simulation harness; on a real
    # booth the account's own home is used and NB_INSTALL/NB_CONFIG are checked.
    check_environment = request.get("home") is None
    layout = MachineLayout(Path(request["home"]) if request.get("home") else Path.home())
    if command == "build":
        result = build(layout, request, check_environment)
    elif command == "activate":
        result = activate(layout, request, check_environment)
    else:
        result = {}
    result["status"] = status(layout, check_environment)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python -m neurobooth_os.deploy.agent REQUEST.json RESULT.json", file=sys.stderr)
        return 2
    request_path, result_path = Path(argv[0]), Path(argv[1])
    try:
        payload = {"ok": True, **handle(json.loads(request_path.read_text(encoding="utf-8")))}
        exit_code = 0
    except (AgentError, SlotError, gitops.GitError) as error:
        log(f"ERROR: {error}")
        payload = {"ok": False, "error": str(error)}
        exit_code = 1
    except Exception as error:  # noqa: BLE001 - reported in the result with its traceback, exit 1
        traceback.print_exc()
        payload = {"ok": False, "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()}
        exit_code = 1
    temporary = result_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    replace_file(temporary, result_path)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
