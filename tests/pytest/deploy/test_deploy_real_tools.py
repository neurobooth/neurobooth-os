"""Deploys that swap a stand-in for the real thing.

* ``test_deploy_with_real_uv`` — real ``uv sync`` / ``uv pip install`` build
  each slot's venv (any OS; skipped when uv is not installed).
* ``test_deploy_through_windows_task_scheduler`` — STM/ACQ/CTR agents run
  through real Task Scheduler tasks on this machine, the same code path CTR
  uses against the booths, minus the cross-machine login. Windows only, and
  opt-in (``NB_DEPLOY_TEST_SCHTASKS=1``) because it creates scheduled tasks.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List

import pytest
from simulated_booth import SimulatedBooth

from neurobooth_os.deploy.orchestrator import Orchestrator
from neurobooth_os.deploy.slots import MachineState, same_path
from neurobooth_os.deploy.transports import SchtasksTransport

REAL_UV = shutil.which("uv")


def make_wheel(directory: Path) -> Path:
    """Build a minimal pure-Python wheel standing in for the Spinnaker SDK."""
    wheel = directory / "spinnaker_python_stub-1.0-py3-none-any.whl"
    dist_info = "spinnaker_python_stub-1.0.dist-info"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("spinnaker_stub.py", "AVAILABLE = True\n")
        archive.writestr(f"{dist_info}/METADATA",
                         "Metadata-Version: 2.1\nName: spinnaker-python-stub\nVersion: 1.0\n")
        archive.writestr(f"{dist_info}/WHEEL",
                         "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        archive.writestr(f"{dist_info}/RECORD", "")
    return wheel


@pytest.mark.skipif(REAL_UV is None, reason="uv is not installed")
def test_deploy_with_real_uv(booth: SimulatedBooth, tmp_path: Path) -> None:
    pyproject = ('[project]\nname = "sim-neurobooth-os"\nversion = "0"\nrequires-python = ">=3.8"\n'
                 'dependencies = []\n\n[project.optional-dependencies]\neyelink = []\n')
    (booth.os_dev / "pyproject.toml").write_text(pyproject)
    (booth.os_dev / "uv.lock").unlink()  # the simulation's placeholder lock, not real TOML
    subprocess.run([REAL_UV, "lock"], cwd=str(booth.os_dev), check=True, capture_output=True)
    booth.commit_os("Real lock", {"pyproject.toml": pyproject,
                                  "uv.lock": (booth.os_dev / "uv.lock").read_text()})
    wheel = make_wheel(tmp_path)
    reference = booth.orchestrator([])
    targets = [dataclasses.replace(t, spinnaker_wheel=str(wheel)) if t.spinnaker_wheel else t
               for t in reference.targets]
    output: List[str] = []
    orchestrator = Orchestrator(booth.environment, targets, reference.ctr_layout,
                                transport_factory=booth.local_transports(), uv=[REAL_UV], output=output.append)

    assert orchestrator.deploy() == 0, "\n".join(output)

    for role, machine in booth.machines.items():
        green = machine.layout.slot_install("green")
        assert (green / ".venv" / "pyvenv.cfg").exists()
        activate = next((green / ".venv").glob("*/activate"))
        # The venv must name its slot's real path, not the NB_INSTALL link, or
        # it would follow the link to the other slot after a switch.
        assert os.path.normcase(str(green)) in os.path.normcase(activate.read_text())
        assert os.path.normcase(str(machine.layout.install_link)) not in os.path.normcase(activate.read_text())
        has_stub = bool(list((green / ".venv").rglob("spinnaker_stub.py")))
        assert has_stub == (role == "ACQ")


@pytest.mark.skipif(sys.platform != "win32", reason="Task Scheduler is Windows-only")
@pytest.mark.skipif(os.environ.get("NB_DEPLOY_TEST_SCHTASKS") != "1",
                    reason="creates scheduled tasks; set NB_DEPLOY_TEST_SCHTASKS=1 to run")
def test_deploy_through_windows_task_scheduler(booth: SimulatedBooth) -> None:
    homes = {machine.name: machine.home for machine in booth.machines.values()}

    def factory(target, run_id):
        if target.role == "CTR":
            return booth.local_transports()(target, run_id)
        home = homes[target.name]
        return SchtasksTransport(target.name, run_id, user=None, password=None, remote_home=str(home),
                                 share_home=home, python_command=[sys.executable], home_override=home,
                                 poll_interval_s=0.5)

    new_sha = booth.commit_os("Change", {"neurobooth_os/a.py": "A = 1\n"})
    output: List[str] = []
    assert booth.orchestrator(output, transport_factory=factory).deploy() == 0, "\n".join(output)
    for role, machine in booth.machines.items():
        state = MachineState.load(machine.layout)
        assert state.active == "green" and state.slots["green"].os_sha == new_sha
        assert same_path(machine.layout.install_link, machine.layout.slot_install("green"))

    assert booth.orchestrator(output, transport_factory=factory).rollback() == 0, "\n".join(output)
    for role in booth.machines:
        assert MachineState.load(booth.machines[role].layout).active == "blue"

    leftover = subprocess.run(["SCHTASKS", "/Query", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=True).stdout
    assert "neurobooth-deploy-" not in leftover, "deploy tasks must be deleted after use"
