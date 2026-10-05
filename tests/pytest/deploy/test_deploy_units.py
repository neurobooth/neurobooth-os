"""Unit tests for the deploy building blocks (any OS)."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest
from simulated_booth import SimulatedBooth, booth_config, run_git

from neurobooth_os.config import ConfigException, NeuroboothConfig
from neurobooth_os.deploy import gitops, schtasks
from neurobooth_os.deploy.agent import environment_problems, write_version_file
from neurobooth_os.deploy.orchestrator import (
    booth_transport_factory,
    machines_from_config,
)
from neurobooth_os.deploy.processes import ProcessInfo, find_install_processes
from neurobooth_os.deploy.slots import (
    MachineLayout,
    MachineState,
    SlotError,
    SlotRecord,
    is_link,
    other_color,
    point_link,
    remove_slot_tree,
    same_path,
)
from neurobooth_os.deploy.transports import SchtasksTransport, TransportError

NAMES = {"CTR": "ctr-x", "STM": "stm-x", "ACQ": "acq-x"}


# -- slots ------------------------------------------------------------------

def test_other_color_flips_and_rejects_unknown() -> None:
    assert other_color("blue") == "green" and other_color("green") == "blue"
    with pytest.raises(SlotError):
        other_color("red")


def test_point_link_creates_then_swaps(tmp_path: Path) -> None:
    blue, green = tmp_path / "blue", tmp_path / "green"
    blue.mkdir(), green.mkdir()
    (blue / "marker").write_text("blue")
    link = tmp_path / "live"

    point_link(link, blue)
    assert is_link(link) and (link / "marker").read_text() == "blue"
    point_link(link, green)
    assert same_path(link, green)
    assert (blue / "marker").exists(), "swapping must never touch the old target's contents"


def test_point_link_refuses_to_replace_a_real_directory(tmp_path: Path) -> None:
    real = tmp_path / "live"
    real.mkdir()
    with pytest.raises(SlotError, match="real directory"):
        point_link(real, tmp_path)


def test_remove_slot_tree_refuses_paths_outside_the_slots(tmp_path: Path) -> None:
    layout = MachineLayout(tmp_path)
    layout.slots_root.mkdir(parents=True)
    outside = tmp_path / "precious"
    outside.mkdir()
    with pytest.raises(SlotError):
        remove_slot_tree(layout, outside)
    assert outside.exists()

    inside = layout.slot_dir("blue") / "config"
    inside.mkdir(parents=True)
    remove_slot_tree(layout, inside)
    assert not inside.exists()


def test_remove_slot_tree_refuses_a_link_into_the_slots(tmp_path: Path) -> None:
    layout = MachineLayout(tmp_path)
    target = layout.slot_dir("blue")
    target.mkdir(parents=True)
    link = layout.slots_root / "alias"
    point_link(link, target)
    with pytest.raises(SlotError):
        remove_slot_tree(layout, link)
    assert target.exists()


def test_machine_state_round_trips(tmp_path: Path) -> None:
    layout = MachineLayout(tmp_path)
    state = MachineState(active="green", previous_active="blue", activated_by_run="r1",
                         slots={"green": SlotRecord(color="green", status="ready", os_sha="a" * 40)})
    state.save(layout)
    assert MachineState.load(layout) == state


# -- version stamps -----------------------------------------------------------

def test_version_file_matches_what_the_bat_scripts_write(tmp_path: Path) -> None:
    # Same text github_checkout.bat / version.bat produce, minus CRLF.
    expected = ('\n\n"""\n    Stores neurobooth version number.\n    GENERATED FILE. DO NOT EDIT MANUALLY\n'
                '"""\n\nversion = \'v0.94.3\'\n')
    path = tmp_path / "current_release.py"
    write_version_file(path, "version number", "v0.94.3")
    assert path.read_text() == expected
    assignment = ast.parse(path.read_text()).body[-1]
    assert isinstance(assignment, ast.Assign) and ast.literal_eval(assignment.value) == "v0.94.3"


@pytest.mark.parametrize("ref, kind, label", [
    ("v1.0.0", "tag", "v1.0.0"),
    ("master", "branch", "master@0123456"),
    ("0123456789" * 4, "commit", "012345678901"),
])
def test_resolved_ref_label(ref: str, kind: str, label: str) -> None:
    assert gitops.ResolvedRef(ref=ref, sha="0123456789" * 4, kind=kind).label == label


# -- gitops ----------------------------------------------------------------------

def test_resolve_remote_ref_finds_branches_annotated_tags_and_commits(tmp_path: Path, git_identity: None) -> None:
    booth = SimulatedBooth(tmp_path)
    master = booth.commit_os("Second", {"x.py": "X = 1\n"})
    booth.tag_os("v2.0.0")
    feature = booth.branch_os("feature", {"y.py": "Y = 1\n"})
    clone = tmp_path / "clone"
    run_git(tmp_path, "clone", "-q", str(booth.os_origin), "clone")

    assert gitops.default_branch(clone) == "master"
    assert gitops.resolve_remote_ref(clone, "master") == gitops.ResolvedRef("master", master, "branch")
    assert gitops.resolve_remote_ref(clone, "feature").sha == feature
    tag = gitops.resolve_remote_ref(clone, "v2.0.0")
    assert tag.kind == "tag" and tag.sha == master, "annotated tags resolve to the commit, not the tag object"
    assert gitops.resolve_remote_ref(clone, master).kind == "commit"
    with pytest.raises(gitops.GitError, match="not a branch or tag"):
        gitops.resolve_remote_ref(clone, "no-such-branch")


# -- processes -----------------------------------------------------------------

def test_find_install_processes_matches_install_paths_and_skips_own_ancestry(tmp_path: Path) -> None:
    install = tmp_path / "nb_os_env" / "neurobooth-os"
    me = os.getpid()
    processes = [
        ProcessInfo(1, 0, "init"),
        ProcessInfo(10, 1, f"python {install}/neurobooth_os/server_stm.py"),
        ProcessInfo(11, 1, f"python {str(install).upper()}\\NEUROBOOTH_OS\\server_acq.py"),
        ProcessInfo(12, 1, f"python {install}-other/thing.py"),
        ProcessInfo(20, 1, f"cmd /c {install}/nb_deploy.bat"),
        ProcessInfo(me, 20, f"python -m neurobooth_os.deploy {install}/x"),
    ]
    found = {process.pid for process in find_install_processes([install], processes)}
    expected = {10}
    if os.name == "nt":
        expected.add(11)  # Windows paths are case-insensitive and use either slash
    assert found == expected


# -- config -> machines ------------------------------------------------------------

def test_machines_from_config_assigns_roles_and_per_machine_steps() -> None:
    targets = machines_from_config(NeuroboothConfig(**booth_config("staging", NAMES)))
    by_role = {target.role: target for target in targets}
    assert targets[-1].role == "CTR", "CTR must switch last"
    assert by_role["STM"].extras == ("eyelink",)
    assert by_role["ACQ"].spinnaker_wheel == "C:/wheels/spinnaker.whl"
    assert by_role["CTR"].labrecorder and not by_role["STM"].labrecorder
    assert by_role["CTR"].extras == () and by_role["CTR"].spinnaker_wheel is None


def test_machines_from_config_requires_a_spinnaker_wheel_for_flir_machines() -> None:
    raw = booth_config("staging", NAMES)
    del raw["machines"]["acq-x"]["spinnaker_wheel"]
    with pytest.raises(ConfigException, match="spinnaker_wheel"):
        machines_from_config(NeuroboothConfig(**raw))


def test_booth_transport_factory_uses_task_scheduler_for_remote_machines() -> None:
    raw = booth_config("staging", NAMES)
    raw["machines"]["acq-x"]["password"] = "pw"
    raw["machines"]["stm-x"]["password"] = "pw"
    targets = {t.role: t for t in machines_from_config(NeuroboothConfig(**raw))}
    acq = booth_transport_factory(targets["ACQ"], "run1")
    assert isinstance(acq, SchtasksTransport)
    assert acq.remote_runtime == "C:\\Users\\SIM_ACQ\\nb_os_env\\deploy_runtime\\run1"
    assert str(acq.share_runtime).startswith("\\\\acq-x\\C$\\Users\\SIM_ACQ")
    assert type(booth_transport_factory(targets["CTR"], "run1")).__name__ == "LocalTransport"


def test_booth_transport_factory_requires_passwords_for_remote_machines() -> None:
    targets = {t.role: t for t in machines_from_config(NeuroboothConfig(**booth_config("staging", NAMES)))}
    with pytest.raises(ConfigException, match="No password"):
        booth_transport_factory(targets["STM"], "run1")


def test_environment_problems_flags_mismatched_variables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = MachineLayout(tmp_path)
    monkeypatch.setenv("NB_INSTALL", str(layout.install_link))
    monkeypatch.setenv("NB_CONFIG", str(tmp_path / "elsewhere"))
    problems = environment_problems(layout)
    assert len(problems) == 1 and "NB_CONFIG" in problems[0]


# -- Task Scheduler transport (SCHTASKS mocked) ---------------------------------------

def test_schtasks_transport_creates_runs_and_deletes_the_task(tmp_path: Path) -> None:
    calls: List[List[str]] = []
    share_home = tmp_path / "share"
    transport = SchtasksTransport("acq-x", "run1", user="SIM_ACQ", password="pw",
                                  remote_home="C:\\Users\\SIM_ACQ", share_home=share_home,
                                  poll_interval_s=0.01)

    def fake_run_cmd(command: List[str], server_name=None, user=None, password=None, **_kwargs) -> str:
        calls.append(command[:2] + [str(server_name), str(user)])
        if command[:2] == ["SCHTASKS", "/Run"]:
            # The agent would now run on the machine and write its result.
            (transport.share_runtime / "status-result.json").write_text(json.dumps({"ok": True, "status": {}}))
        return ""

    with patch.object(schtasks, "run_cmd", side_effect=fake_run_cmd):
        result = transport.run({"command": "status", "run_id": "run1"}, timeout_s=5)
        transport.close()

    assert result.ok
    assert [call[:2] for call in calls] == [
        ["net", "use"], ["SCHTASKS", "/Create"], ["SCHTASKS", "/Run"], ["SCHTASKS", "/Delete"], ["net", "use"],
    ]
    assert all(call[2:] == ["acq-x", "SIM_ACQ"] for call in calls if call[0] == "SCHTASKS")
    bat = (transport.share_runtime / "status.bat").read_text()
    assert '"uv" "run" "--no-project" "python" -m neurobooth_os.deploy.agent' in bat
    assert (transport.share_runtime / "neurobooth_os" / "deploy" / "agent.py").exists()
    request = json.loads((transport.share_runtime / "status-request.json").read_text())
    assert request["home"] is None, "on a real booth the agent uses the account's own home"


def test_schtasks_transport_times_out_and_still_deletes_the_task(tmp_path: Path) -> None:
    deleted = []

    def fake_run_cmd(command: List[str], *_args, **_kwargs) -> str:
        if command[:2] == ["SCHTASKS", "/Delete"]:
            deleted.append(True)
        return ""

    transport = SchtasksTransport("acq-x", "run1", user="SIM_ACQ", password="pw",
                                  remote_home="C:\\Users\\SIM_ACQ", share_home=tmp_path, poll_interval_s=0.01)
    with patch.object(schtasks, "run_cmd", side_effect=fake_run_cmd),             pytest.raises(TransportError, match="no result after"):
        transport.run({"command": "status", "run_id": "run1"}, timeout_s=0.05)
    assert deleted == [True]


def test_build_task_xml_passes_arguments_through() -> None:
    xml = schtasks.build_task_xml(r"C:\x\run.bat", arguments="a & b")
    assert "<Arguments>a &amp; b</Arguments>" in xml
    assert "<Arguments>" not in schtasks.build_task_xml(r"C:\x\run.bat")


def test_git_wrapper_reports_stderr(tmp_path: Path) -> None:
    with pytest.raises(gitops.GitError, match="not a git repository|cannot change"):
        gitops.head_sha(tmp_path)


def test_agent_writes_a_result_even_when_the_request_is_invalid(tmp_path: Path) -> None:
    request, result = tmp_path / "request.json", tmp_path / "result.json"
    request.write_text(json.dumps({"command": "explode", "home": str(tmp_path)}))
    completed = subprocess.run(
        [sys.executable, "-m", "neurobooth_os.deploy.agent", str(request), str(result)],
        cwd=str(Path(__file__).resolve().parents[3]), capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(result.read_text())
    assert payload["ok"] is False and "Unknown command" in payload["error"]
