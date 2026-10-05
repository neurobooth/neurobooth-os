"""A three-machine booth environment simulated in a temporary directory.

Stands in for CTR/STM/ACQ without the hardware or network: each "machine" is
a home directory, the two GitHub repos are local bare repos, and ``uv`` is
``fake_uv.py``. The deploy code runs unmodified against it, through
:class:`LocalTransport` or (on Windows) the real Task Scheduler.

The machines start in today's layout — a plain neurobooth-os checkout at
``nb_os_env/neurobooth-os`` and a config copied into ``.neurobooth_os`` — so
the first deploy exercises adoption into the blue/green layout.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from neurobooth_os.config import NeuroboothConfig
from neurobooth_os.deploy.orchestrator import (
    Orchestrator,
    TransportFactory,
    machines_from_config,
)
from neurobooth_os.deploy.slots import MachineLayout
from neurobooth_os.deploy.transports import LocalTransport

FAKE_UV = [sys.executable, str(Path(__file__).with_name("fake_uv.py"))]

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Deploy Test", "GIT_AUTHOR_EMAIL": "deploy-test@example.invalid",
    "GIT_COMMITTER_NAME": "Deploy Test", "GIT_COMMITTER_EMAIL": "deploy-test@example.invalid",
}

VERSION_SENTINEL = '\n\n"""\n    GENERATED FILE. DO NOT EDIT MANUALLY\n"""\n\nversion = \'NO VERSION SET\'\n'


def run_git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {completed.stderr}")
    return completed.stdout.strip()


def booth_config(environment: str, machine_names: Dict[str, str]) -> Dict:
    """A minimal valid neurobooth_os_config.yaml for the simulated machines."""
    ctr, stm, acq = machine_names["CTR"], machine_names["STM"], machine_names["ACQ"]
    return {
        "environment": environment,
        "remote_data_dir": "Z:/data/",
        "video_task_dir": "C:/videos",
        "split_xdf_backlog": "C:/backlog.csv",
        "cam_inx_lowfeed": 0,
        "default_preview_stream": "IPhoneFrameIndex",
        "screen": {"fullscreen": False, "width_cm": 55, "subject_distance_to_screen_cm": 60,
                   "min_refresh_rate_hz": 200, "max_refresh_rate_hz": 250,
                   "screen_resolution": [1920, 1080]},
        "machines": {
            acq: {"user": "SIM_ACQ", "local_data_dir": "C:/data", "spinnaker_wheel": "C:/wheels/spinnaker.whl"},
            stm: {"user": "SIM_STM", "local_data_dir": "C:/data"},
            ctr: {"user": "SIM_CTR", "local_data_dir": "C:/data"},
        },
        "acquisition": [
            {"machine": acq, "devices": ["FLIR_blackfly_1", "Intel_D455_1"]},
            {"machine": stm, "devices": ["Mouse"]},
        ],
        "presentation": {"machine": stm, "devices": ["Eyelink_1", "marker"]},
        "control": {"machine": ctr},
        "database": {"dbname": "sim", "user": "sim", "password": "unused", "host": "localhost",
                     "port": 5432, "ssh_tunnel": False, "remote_user": "sim", "remote_host": "localhost"},
    }


@dataclass
class SimMachine:
    name: str
    role: str
    home: Path

    @property
    def layout(self) -> MachineLayout:
        return MachineLayout(self.home)


class SimulatedBooth:
    """Origins, a developer clone of each repo, and three booth machines."""

    def __init__(self, root: Path, environment: str = "staging") -> None:
        self.root = root
        self.environment = environment
        self.machines = {
            role: SimMachine(f"{role.lower()}-sim", role, root / "machines" / role.lower())
            for role in ("CTR", "STM", "ACQ")
        }
        self.os_origin = root / "origins" / "neurobooth-os.git"
        self.configs_origin = root / "origins" / "configs.git"
        self.os_dev = root / "dev" / "neurobooth-os"
        self.configs_dev = root / "dev" / "configs"
        self._create_origins()

    # -- repos -------------------------------------------------------------

    def _create_origins(self) -> None:
        for origin, dev, branch in ((self.os_origin, self.os_dev, "master"),
                                    (self.configs_origin, self.configs_dev, "main")):
            origin.mkdir(parents=True)
            run_git(origin, "init", "--bare", "-b", branch)
            dev.parent.mkdir(parents=True, exist_ok=True)
            run_git(dev.parent, "clone", str(origin), dev.name)
            run_git(dev, "checkout", "-b", branch)

        self.commit(self.os_dev, "Initial neurobooth-os", {
            "neurobooth_os/__init__.py": '"""Neurobooth OS"""\n',
            "neurobooth_os/current_release.py": VERSION_SENTINEL,
            "neurobooth_os/current_config.py": VERSION_SENTINEL,
            "neurobooth_os/server_stm.py": "import time\ntime.sleep(120)\n",
            "pyproject.toml": '[project]\nname = "sim-neurobooth-os"\nversion = "0"\nrequires-python = ">=3.8"\n'
                              'dependencies = []\n',
            "uv.lock": "lock v1\n",
        })
        names = {role: machine.name for role, machine in self.machines.items()}
        files = {"shared/shared_setting.yaml": "shared: 1\n", ".gitignore": "secrets.yaml\n"}
        for environment in ("staging", "merrimac"):
            files[f"environments/{environment}/neurobooth_os_config.yaml"] = yaml.safe_dump(
                booth_config(environment, names))
        self.commit(self.configs_dev, "Initial configs", files)

    @staticmethod
    def commit(dev: Path, message: str, files: Dict[str, str], delete: Optional[List[str]] = None) -> str:
        """Commit ``files`` (path -> content) on the dev clone's branch and push it."""
        for relative, content in files.items():
            path = dev / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for relative in delete or []:
            run_git(dev, "rm", "-q", relative)
        run_git(dev, "add", "-A")
        run_git(dev, "commit", "-q", "-m", message)
        run_git(dev, "push", "-q", "origin", "HEAD")
        return run_git(dev, "rev-parse", "HEAD")

    def commit_os(self, message: str, files: Dict[str, str], delete: Optional[List[str]] = None) -> str:
        return self.commit(self.os_dev, message, files, delete)

    def commit_configs(self, message: str, files: Dict[str, str]) -> str:
        return self.commit(self.configs_dev, message, files)

    def branch_os(self, branch: str, files: Dict[str, str]) -> str:
        """Commit ``files`` on a new branch of neurobooth-os, leaving master where it was."""
        run_git(self.os_dev, "checkout", "-q", "-b", branch)
        sha = self.commit(self.os_dev, f"Work on {branch}", files)
        run_git(self.os_dev, "checkout", "-q", "master")
        return sha

    def tag_os(self, tag: str) -> None:
        run_git(self.os_dev, "tag", "-a", tag, "-m", tag)
        run_git(self.os_dev, "push", "-q", "origin", tag)

    # -- machines ----------------------------------------------------------

    def install_legacy(self) -> None:
        """Set every machine up the way the booths are today (pre-blue-green)."""
        for machine in self.machines.values():
            layout = machine.layout
            layout.nb_root.mkdir(parents=True)
            run_git(layout.nb_root, "clone", "-q", str(self.os_origin), "neurobooth-os")
            run_git(layout.nb_root, "clone", "-q", str(self.configs_origin), "configs")
            (layout.install_link / ".venv").mkdir()
            (layout.install_link / ".venv" / "legacy-venv").write_text("built at the old path\n")
            secrets = layout.configs_repo / "environments" / self.environment / "secrets.yaml"
            secrets.write_text(f"{self.environment}:\n  database:\n    password: sim-secret\n")
            # What configs/deploy.bat does today.
            shutil.copytree(layout.configs_repo / "shared", layout.config_link)
            shutil.copytree(layout.configs_repo / "environments" / self.environment, layout.config_link,
                            dirs_exist_ok=True)

    def config(self) -> NeuroboothConfig:
        live = self.machines["CTR"].layout.config_link / "neurobooth_os_config.yaml"
        return NeuroboothConfig(**yaml.safe_load(live.read_text(encoding="utf-8")))

    def local_transports(self) -> TransportFactory:
        homes = {machine.name: machine.home for machine in self.machines.values()}
        return lambda target, run_id: LocalTransport(target.name, run_id, home=homes[target.name])

    def orchestrator(self, output: List[str], transport_factory: Optional[TransportFactory] = None,
                     uv: Optional[List[str]] = None) -> Orchestrator:
        return Orchestrator(
            environment=self.environment,
            targets=machines_from_config(self.config()),
            ctr_layout=self.machines["CTR"].layout,
            transport_factory=transport_factory or self.local_transports(),
            uv=uv or FAKE_UV,
            output=output.append,
        )
