"""Tests for ``neurobooth_os.deploy_all``.

The Task Scheduler tests create, run and poll a real task on this machine:
a machine with an empty user makes ``_run_cmd`` skip ``/S /U /P``, so the
same code path runs locally. The other machines of a real booth are not
reachable from a test.
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List, Tuple

import pytest
from pydantic import SecretStr

from neurobooth_os import config, deploy_all
from neurobooth_os.config import MachineSpec

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="uses Windows Task Scheduler")


def _machine(user: str, password: str = "secret") -> MachineSpec:
    return MachineSpec(user=user, password=SecretStr(password), local_data_dir="C:/data")


def _plan(repo_dir: Path, script_args: List[str]) -> deploy_all.DeployPlan:
    return deploy_all.DeployPlan(repo_dir, script_args, repo_dir / "neurobooth_os_config.yaml")


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo folder that deploy_remote treats as the remote machine's copy."""
    monkeypatch.setattr(deploy_all, "remote_repo_dir", lambda repo_dir, user: tmp_path)
    yield tmp_path
    subprocess.run(["SCHTASKS", "/Delete", "/TN", deploy_all.TASK_NAME, "/F"],
                   capture_output=True)


# ---------------------------------------------------------------------------
# plan_from_args
# ---------------------------------------------------------------------------


def test_neurobooth_os_plan_runs_github_checkout_with_machines_from_nb_config(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NB_CONFIG", str(tmp_path / "config"))
    plan = deploy_all.plan_from_args(["neurobooth-os", str(tmp_path), "v1.2.3"])
    assert plan.script_args == ["github_checkout.bat", "v1.2.3"]
    assert plan.config_path == tmp_path / "config" / "neurobooth_os_config.yaml"


def test_configs_plan_runs_checkout_and_deploy_with_machines_from_the_environment(
        tmp_path: Path) -> None:
    (tmp_path / "environments" / "staging").mkdir(parents=True)
    plan = deploy_all.plan_from_args(["configs", str(tmp_path), "v1.2.3", "staging"])
    assert plan.script_args == ["checkout_and_deploy.bat", "v1.2.3", "staging"]
    assert plan.config_path == tmp_path / "environments" / "staging" / "neurobooth_os_config.yaml"


def test_unknown_environment_lists_the_valid_names(tmp_path: Path) -> None:
    for name in ("staging", "wang"):
        (tmp_path / "environments" / name).mkdir(parents=True)
    with pytest.raises(ValueError, match="'stagging' is not an environment. Valid names: staging, wang"):
        deploy_all.plan_from_args(["configs", str(tmp_path), "v1.2.3", "stagging"])


@pytest.mark.parametrize("arguments", [
    [],
    ["neurobooth-os", "C:/repo"],
    ["neurobooth-os", "C:/repo", "v1", "staging"],
    ["configs", "C:/repo", "v1"],
])
def test_wrong_arguments_show_usage(arguments: List[str]) -> None:
    with pytest.raises(ValueError, match="Usage"):
        deploy_all.plan_from_args(arguments)


# ---------------------------------------------------------------------------
# check_ref_exists
# ---------------------------------------------------------------------------


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com",
                    *arguments], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def clone_of_tagged_origin(tmp_path: Path) -> Path:
    """A clone whose origin gets tag v1.0.0 only after the clone was made."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q")
    _git(origin, "commit", "-q", "--allow-empty", "-m", "first")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(origin, "tag", "v1.0.0")
    return clone


def test_ref_check_fetches_then_finds_a_new_tag(clone_of_tagged_origin: Path) -> None:
    deploy_all.check_ref_exists(_plan(clone_of_tagged_origin, ["github_checkout.bat", "v1.0.0"]))


def test_ref_check_rejects_a_missing_tag_before_any_machine(clone_of_tagged_origin: Path) -> None:
    with pytest.raises(RuntimeError, match="'v0.96.0' is not a tag or branch .* No machine was changed"):
        deploy_all.check_ref_exists(_plan(clone_of_tagged_origin, ["github_checkout.bat", "v0.96.0"]))


def test_ref_check_reports_a_failed_fetch(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="git fetch failed"):
        deploy_all.check_ref_exists(_plan(tmp_path, ["github_checkout.bat", "v1.0.0"]))


# ---------------------------------------------------------------------------
# deploy_everywhere
# ---------------------------------------------------------------------------


@pytest.fixture
def staging_machines(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, str]]:
    """Three staging machines, with this test run's user as ACQ. Records deploys."""
    monkeypatch.setenv("USERNAME", "TEST_ACQ")
    machines = {
        "acq-staging": _machine("TEST_ACQ"),
        "stm-staging": _machine("TEST_STM"),
        "ctr-staging": _machine("TEST_CTR"),
    }
    monkeypatch.setattr(config, "load_neurobooth_config",
                        lambda path: setattr(config, "neurobooth_config",
                                             SimpleNamespace(machines=machines)))
    deploys: List[Tuple[str, str]] = []
    monkeypatch.setattr(deploy_all, "deploy_remote",
                        lambda host, machine, plan: deploys.append(("remote", host)))
    monkeypatch.setattr(deploy_all, "deploy_local",
                        lambda plan: deploys.append(("local", "here")))
    return deploys


def test_deploys_other_machines_first_and_this_one_last(
        staging_machines: List[Tuple[str, str]], tmp_path: Path) -> None:
    assert deploy_all.deploy_everywhere(_plan(tmp_path, ["github_checkout.bat", "v1"])) == 0
    assert staging_machines == [("remote", "stm-staging"), ("remote", "ctr-staging"),
                                ("local", "here")]


def test_stops_at_the_first_failure(staging_machines: List[Tuple[str, str]], tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture) -> None:
    def fail(host: str, machine: MachineSpec, plan: deploy_all.DeployPlan) -> None:
        raise RuntimeError("simulated")

    monkeypatch.setattr(deploy_all, "deploy_remote", fail)
    assert deploy_all.deploy_everywhere(_plan(tmp_path, ["github_checkout.bat", "v1"])) == 1
    assert staging_machines == []
    assert "Not started: ['ctr-staging', 'acq-staging']" in capsys.readouterr().out


def test_refuses_when_this_machine_is_not_in_the_environment(
        staging_machines: List[Tuple[str, str]], tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERNAME", "SOMEONE_ELSE")
    assert deploy_all.deploy_everywhere(_plan(tmp_path, ["github_checkout.bat", "v1"])) == 1
    assert staging_machines == []


# ---------------------------------------------------------------------------
# deploy_remote, against this machine's Task Scheduler
# ---------------------------------------------------------------------------


def test_missing_password_names_the_machine(tmp_path: Path) -> None:
    machine = MachineSpec(user="TEST_STM", local_data_dir="C:/data")
    with pytest.raises(RuntimeError, match="machines.stm-staging.password"):
        deploy_all.deploy_remote("stm-staging", machine, _plan(tmp_path, ["x.bat"]))


@windows_only
def test_remote_deploy_runs_the_script_in_the_repo_and_waits(fake_repo: Path) -> None:
    (fake_repo / "fake_deploy.bat").write_text("@echo off\r\necho deployed %1 in %CD%\r\n")
    deploy_all.deploy_remote("localhost", _machine(""), _plan(fake_repo, ["fake_deploy.bat", "v9"]))
    log = (fake_repo / deploy_all.LOG_NAME).read_text()
    assert f"deployed v9 in {fake_repo}" in log


@windows_only
def test_remote_deploy_failure_reports_exit_code_and_log(fake_repo: Path) -> None:
    (fake_repo / "fake_deploy.bat").write_text("@echo off\r\nexit /b 3\r\n")
    with pytest.raises(RuntimeError, match=r"exit code 3\)\. See .*deploy_all\.log"):
        deploy_all.deploy_remote("localhost", _machine(""), _plan(fake_repo, ["fake_deploy.bat"]))


@windows_only
def test_local_deploy_failure_reports_exit_code(tmp_path: Path) -> None:
    (tmp_path / "fake_deploy.bat").write_text("@echo off\r\nexit /b 4\r\n")
    with pytest.raises(RuntimeError, match="exit code 4"):
        deploy_all.deploy_local(_plan(tmp_path, ["fake_deploy.bat"]))
