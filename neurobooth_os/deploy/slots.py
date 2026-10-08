"""Blue-green install slots on one booth machine.

Layout under the booth account's home directory::

    nb_os_env/
        neurobooth-os  -> slots/<active>/neurobooth-os   (link; == %NB_INSTALL%)
        configs/                                          (configs repo checkout)
        slots/
            state.json
            blue/neurobooth-os/   blue/config/
            green/neurobooth-os/  green/config/
        deploy_runtime/<run_id>/                          (agent copy + logs)
    .neurobooth_os     -> nb_os_env/slots/<active>/config (link; == %NB_CONFIG%)

``NB_INSTALL`` and ``NB_CONFIG`` keep their existing values; only the link
targets change, so switching or rolling back is two link swaps. Each slot
has its own git checkout and its own ``.venv``, built at the slot's real path,
so a slot never refers to code in the other slot.

The links are directory junctions on Windows (no admin rights or developer
mode needed) and symlinks elsewhere.

Standard library only (see the package docstring).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

COLORS = ("blue", "green")

# Slot lifecycle. Only READY slots can be activated.
BUILDING = "building"
READY = "ready"
FAILED = "failed"

_IO_REPARSE_TAG_MOUNT_POINT = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


class SlotError(Exception):
    """A slot operation could not be completed safely."""


def other_color(color: str) -> str:
    """Return the slot color that is not ``color``."""
    if color not in COLORS:
        raise SlotError(f"Unknown slot color '{color}'")
    return COLORS[1] if color == COLORS[0] else COLORS[0]


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class MachineLayout:
    """Paths of one booth account's install, rooted at its home directory."""

    home: Path

    @property
    def nb_root(self) -> Path:
        return self.home / "nb_os_env"

    @property
    def install_link(self) -> Path:
        """``%NB_INSTALL%``."""
        return self.nb_root / "neurobooth-os"

    @property
    def config_link(self) -> Path:
        """``%NB_CONFIG%``."""
        return self.home / ".neurobooth_os"

    @property
    def configs_repo(self) -> Path:
        return self.nb_root / "configs"

    @property
    def slots_root(self) -> Path:
        return self.nb_root / "slots"

    @property
    def state_file(self) -> Path:
        return self.slots_root / "state.json"

    @property
    def runtime_root(self) -> Path:
        return self.nb_root / "deploy_runtime"

    def slot_dir(self, color: str) -> Path:
        if color not in COLORS:
            raise SlotError(f"Unknown slot color '{color}'")
        return self.slots_root / color

    def slot_install(self, color: str) -> Path:
        return self.slot_dir(color) / "neurobooth-os"

    def slot_config(self, color: str) -> Path:
        return self.slot_dir(color) / "config"


@dataclass
class SlotRecord:
    """What is built in one slot."""

    color: str
    status: str
    os_ref: str = ""
    os_sha: str = ""
    config_ref: str = ""
    config_sha: str = ""
    environment: str = ""
    run_id: str = ""
    built_at: str = ""
    # True for a slot created by adopting a pre-blue-green install in place.
    # Its venv was built at the old path, so it is rebuilt from scratch the
    # next time this slot is the build target.
    adopted: bool = False


@dataclass
class MachineState:
    """Contents of ``slots/state.json``."""

    active: Optional[str] = None
    previous_active: Optional[str] = None
    activated_by_run: str = ""
    activated_at: str = ""
    slots: Dict[str, SlotRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, layout: MachineLayout) -> MachineState:
        if not layout.state_file.exists():
            return cls()
        raw = json.loads(layout.state_file.read_text(encoding="utf-8"))
        slots = {color: SlotRecord(**record) for color, record in raw.pop("slots", {}).items()}
        return cls(slots=slots, **raw)

    def save(self, layout: MachineLayout) -> None:
        layout.slots_root.mkdir(parents=True, exist_ok=True)
        temporary = layout.state_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        replace_file(temporary, layout.state_file)


def replace_file(source: Path, destination: Path, attempts: int = 20) -> None:
    """``os.replace`` that rides out Windows' transient sharing violations.

    Antivirus and the search indexer briefly open files that were just
    written, and Windows refuses to replace a file another process has open.
    Retries for up to ~2 s, then lets the PermissionError propagate.
    """
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if sys.platform != "win32" or attempt == attempts - 1:
                raise
            time.sleep(0.1)


def is_link(path: Path) -> bool:
    """True if ``path`` is a symlink or a Windows directory junction."""
    try:
        path_stat = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(path_stat.st_mode):
        return True
    return getattr(path_stat, "st_reparse_tag", 0) == _IO_REPARSE_TAG_MOUNT_POINT


def same_path(first: Path, second: Path) -> bool:
    """Compare two paths after resolving links and normalizing case."""
    return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))


def _create_link(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            raise SlotError(f"mklink /J {link} -> {target} failed: {completed.stdout}{completed.stderr}")
    else:
        os.symlink(target, link, target_is_directory=True)


def _remove_link(link: Path) -> None:
    if not is_link(link):
        raise SlotError(f"Refusing to remove {link}: it is not a link")
    if sys.platform == "win32":
        os.rmdir(link)  # removes the junction itself, never the target's contents
    else:
        os.unlink(link)


def point_link(link: Path, target: Path) -> None:
    """Make ``link`` point at ``target``, replacing an existing link.

    On POSIX the swap is a single atomic rename. Windows cannot rename over an
    existing junction, so there the old junction is removed first; the gap is
    a few microseconds and deploys only switch while no booth process runs.

    Raises:
        SlotError: ``link`` exists and is a real directory or file.
    """
    if link.exists() and not is_link(link):
        raise SlotError(f"{link} is a real directory, not a link; it must be adopted first")
    staged = link.with_name(link.name + ".deploy-new")
    if is_link(staged):
        _remove_link(staged)
    _create_link(staged, target)
    if sys.platform == "win32":
        if is_link(link):
            _remove_link(link)
        os.rename(staged, link)
    else:
        os.replace(staged, link)


def remove_slot_tree(layout: MachineLayout, path: Path) -> None:
    """Delete a directory inside the slots tree, refusing anything outside it.

    Guards against a misconfigured path turning into a recursive delete of
    something that is not ours.
    """
    if not path.exists():
        return
    slots_root = os.path.normcase(os.path.realpath(layout.slots_root))
    resolved = os.path.normcase(os.path.realpath(path))
    if is_link(path) or not resolved.startswith(slots_root + os.sep):
        raise SlotError(f"Refusing to delete {path}: not a real directory inside {layout.slots_root}")

    def _clear_readonly_and_retry(function, failed_path, _exc_info):
        # git marks pack files read-only, which blocks deletion on Windows.
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    shutil.rmtree(path, onerror=_clear_readonly_and_retry)
