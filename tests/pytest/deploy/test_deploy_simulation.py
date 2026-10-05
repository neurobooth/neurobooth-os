"""End-to-end deploys against a simulated three-machine booth (any OS).

Each test drives the real orchestrator and agent; only the machines (temp
home directories), GitHub (local bare repos) and uv (fake_uv.py) are stand-ins.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import pytest
from simulated_booth import SimulatedBooth

from neurobooth_os.deploy.orchestrator import DeployError
from neurobooth_os.deploy.slots import MachineState, is_link, same_path


def read_version(install: Path, name: str = "current_release.py") -> str:
    text = (install / "neurobooth_os" / name).read_text(encoding="utf-8")
    return text.split("version = ")[1].strip().strip("'")


def active_state(booth: SimulatedBooth, role: str) -> MachineState:
    return MachineState.load(booth.machines[role].layout)


def deploy(booth: SimulatedBooth, **kwargs) -> List[str]:
    output: List[str] = []
    exit_code = booth.orchestrator(output).deploy(**kwargs)
    assert exit_code == 0, "\n".join(output)
    return output


def test_first_deploy_adopts_legacy_install_and_switches_every_machine(booth: SimulatedBooth) -> None:
    new_sha = booth.commit_os("Fix a bug", {"neurobooth_os/fix.py": "FIXED = True\n"})

    output = deploy(booth)

    assert any("neurobooth-os master@" + new_sha[:7] in line for line in output)
    for role, machine in booth.machines.items():
        layout = machine.layout
        state = active_state(booth, role)
        assert state.active == "green" and state.previous_active == "blue"
        assert is_link(layout.install_link) and is_link(layout.config_link)
        assert same_path(layout.install_link, layout.slot_install("green"))
        assert same_path(layout.config_link, layout.slot_config("green"))
        # The pre-blue-green install was kept intact as the blue slot.
        assert state.slots["blue"].adopted
        assert (layout.slot_install("blue") / ".venv" / "legacy-venv").exists()
        assert not (layout.slot_install("blue") / "neurobooth_os" / "fix.py").exists()
        # The new code, version stamps and config are live through the links.
        assert (layout.install_link / "neurobooth_os" / "fix.py").exists()
        assert read_version(layout.install_link) == f"master@{new_sha[:7]}"
        assert read_version(layout.install_link, "current_config.py").startswith("main@")
        assert (layout.config_link / "shared_setting.yaml").exists()
        assert (layout.config_link / "secrets.yaml").exists(), "untracked secrets must survive the deploy"
        # uv ran in the slot's real directory, not through the link.
        sync = json.loads((layout.slot_install("green") / ".venv" / "sync.json").read_text())
        assert same_path(Path(sync["cwd"]), layout.slot_install("green"))
        assert not is_link(Path(sync["cwd"]))
        assert sync["nb_install"] == str(layout.slot_install("green"))
        assert sync["virtual_env"] is None

    stm_sync = json.loads((booth.machines["STM"].layout.slot_install("green") / ".venv" / "sync.json").read_text())
    assert "--extra=eyelink" in stm_sync["arguments"]
    acq_wheel = booth.machines["ACQ"].layout.slot_install("green") / ".venv" / "pip_install.json"
    assert "C:/wheels/spinnaker.whl" in json.loads(acq_wheel.read_text())["arguments"]
    assert not (booth.machines["CTR"].layout.slot_install("green") / ".venv" / "pip_install.json").exists()


def test_deploy_with_nothing_pending_changes_nothing(booth: SimulatedBooth) -> None:
    booth.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})
    deploy(booth)
    history = booth.machines["CTR"].layout.slots_root / "history.jsonl"
    entries_before = history.read_text().splitlines()

    output = deploy(booth)

    assert any("Nothing to deploy" in line for line in output)
    assert history.read_text().splitlines() == entries_before
    assert active_state(booth, "STM").active == "green"


def test_rollback_switches_back_and_a_second_rollback_reapplies(booth: SimulatedBooth) -> None:
    ctr_install = booth.machines["CTR"].layout.install_link
    old_version = subprocess.run(["git", "-C", str(ctr_install), "rev-parse", "HEAD"],
                                 capture_output=True, text=True, check=True).stdout.strip()
    new_sha = booth.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})
    deploy(booth)

    output: List[str] = []
    started = time.monotonic()
    assert booth.orchestrator(output).rollback() == 0, "\n".join(output)
    rollback_seconds = time.monotonic() - started

    for role, machine in booth.machines.items():
        assert active_state(booth, role).active == "blue"
        assert same_path(machine.layout.install_link, machine.layout.slot_install("blue"))
        head = subprocess.run(["git", "-C", str(machine.layout.install_link), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        assert head == old_version
    # No rebuild: rollback is link swaps only. Generous bound for slow CI disks.
    assert rollback_seconds < 60

    assert booth.orchestrator(output).rollback() == 0, "\n".join(output)
    for role in booth.machines:
        assert active_state(booth, role).active == "green"
    assert read_version(booth.machines["ACQ"].layout.install_link) == f"master@{new_sha[:7]}"


def test_second_deploy_builds_into_the_old_slot_and_rebuilds_the_adopted_venv(booth: SimulatedBooth) -> None:
    booth.commit_os("First", {"neurobooth_os/a.py": "A = 1\n"})
    deploy(booth)
    second = booth.commit_os("Second", {"neurobooth_os/b.py": "B = 1\n", "uv.lock": "lock v2\n"})

    deploy(booth)

    for role, machine in booth.machines.items():
        state = active_state(booth, role)
        assert state.active == "blue" and state.previous_active == "green"
        blue = state.slots["blue"]
        assert blue.os_sha == second and not blue.adopted
        venv = machine.layout.slot_install("blue") / ".venv"
        assert not (venv / "legacy-venv").exists(), "the adopted venv must be rebuilt from scratch"
        assert json.loads((venv / "sync.json").read_text())["lock"] == "lock v2\n"
        # The previous release stays built in green for rollback.
        assert state.slots["green"].status == "ready"


def test_branch_override_deploys_that_branch(booth: SimulatedBooth) -> None:
    feature = booth.branch_os("123-new-task", {"neurobooth_os/new_task.py": "NEW = True\n"})

    deploy(booth, os_ref="123-new-task")

    for machine in booth.machines.values():
        assert (machine.layout.install_link / "neurobooth_os" / "new_task.py").exists()
        assert read_version(machine.layout.install_link) == f"123-new-task@{feature[:7]}"


def test_tag_deploy_stamps_the_tag(booth: SimulatedBooth) -> None:
    booth.commit_os("Release", {"neurobooth_os/a.py": "A = 1\n"})
    booth.tag_os("v1.2.3")

    deploy(booth, os_ref="v1.2.3")

    assert read_version(booth.machines["STM"].layout.install_link) == "v1.2.3"


def test_production_environment_requires_explicit_refs(tmp_path: Path, git_identity: None) -> None:
    production = SimulatedBooth(tmp_path, environment="merrimac")
    production.install_legacy()
    production.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})

    with pytest.raises(DeployError, match="production environment"):
        production.orchestrator([]).deploy()
    with pytest.raises(DeployError, match="production environment"):
        production.orchestrator([]).deploy(os_ref="master")
    assert active_state(production, "CTR").active is None, "nothing may change"

    output: List[str] = []
    assert production.orchestrator(output).deploy(os_ref="master", config_ref="main") == 0, "\n".join(output)
    assert active_state(production, "CTR").active == "green"


def test_failed_build_switches_no_machine(booth: SimulatedBooth) -> None:
    booth.commit_os("Good", {"neurobooth_os/a.py": "A = 1\n"})
    deploy(booth)
    booth.commit_os("Broken lock", {"FAIL_SYNC": "x\n"})

    output: List[str] = []
    assert booth.orchestrator(output).deploy() == 1

    assert any("build FAILED" in line for line in output)
    assert any("Nothing was switched" in line for line in output)
    for role, machine in booth.machines.items():
        state = active_state(booth, role)
        assert state.active == "green"
        assert state.slots["blue"].status == "failed"
        assert not (machine.layout.install_link / "FAIL_SYNC").exists()


def test_running_booth_process_blocks_the_deploy_before_anything_changes(booth: SimulatedBooth) -> None:
    booth.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})
    stm_server = booth.machines["STM"].layout.install_link / "neurobooth_os" / "server_stm.py"
    server = subprocess.Popen([sys.executable, str(stm_server)])
    try:
        output: List[str] = []
        with pytest.raises(DeployError, match="Blocked"):
            booth.orchestrator(output).deploy()
        assert any("stm-sim: running from the install" in line for line in output)
        for role in booth.machines:
            assert active_state(booth, role).active is None, f"{role} must be untouched"
    finally:
        server.kill()
        server.wait()

    deploy(booth)
    assert active_state(booth, "STM").active == "green"


def test_uncommitted_config_edits_block_the_deploy(booth: SimulatedBooth) -> None:
    booth.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})
    edited = booth.machines["ACQ"].layout.configs_repo / "shared" / "shared_setting.yaml"
    edited.write_text("shared: 2  # hand edit on the booth\n")

    output: List[str] = []
    with pytest.raises(DeployError, match="Blocked"):
        booth.orchestrator(output).deploy()

    assert any("acq-sim:" in line and "uncommitted changes" in line for line in output)
    assert edited.read_text().startswith("shared: 2"), "the hand edit must not be discarded"


def test_dry_run_reports_without_changing_anything(booth: SimulatedBooth) -> None:
    booth.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})

    output: List[str] = []
    assert booth.orchestrator(output).deploy(dry_run=True) == 0

    assert any(line.startswith("Dry run: would deploy to") for line in output)
    for machine in booth.machines.values():
        assert not machine.layout.slots_root.exists()
        assert not is_link(machine.layout.install_link)


def test_status_reports_both_slots(booth: SimulatedBooth) -> None:
    booth.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})
    deploy(booth)

    output: List[str] = []
    assert booth.orchestrator(output).status() == 0

    text = "\n".join(output)
    assert "stm-sim (STM) — layout: slots, active: green" in text
    assert "* green" in text and "  blue " in text
