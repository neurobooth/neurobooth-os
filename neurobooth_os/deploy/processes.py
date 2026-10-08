"""Detect booth processes that would be disrupted by a deploy.

A deploy refuses to touch a machine while anything is running out of its
install (servers, the CTR GUI, ad-hoc scripts): a participant session may be
in progress, and Windows cannot replace files a running process has open.

Standard library only (see the package docstring).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int
    command_line: str


def list_processes() -> List[ProcessInfo]:
    """Return every process visible to this account with its command line."""
    if sys.platform == "win32":
        output = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             ("Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")],
            capture_output=True, text=True, check=True,
        ).stdout
        rows = json.loads(output) if output.strip() else []
        if isinstance(rows, dict):
            rows = [rows]
        return [
            ProcessInfo(int(row["ProcessId"]), int(row["ParentProcessId"] or 0), row["CommandLine"] or "")
            for row in rows
        ]
    output = subprocess.run(
        ["ps", "-A", "-ww", "-o", "pid=", "-o", "ppid=", "-o", "command="],
        capture_output=True, text=True, check=True,
    ).stdout
    processes = []
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            processes.append(ProcessInfo(int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return processes


def _ancestors(pid: int, parents: Dict[int, int]) -> Set[int]:
    seen: Set[int] = set()
    while pid and pid not in seen:
        seen.add(pid)
        pid = parents.get(pid, 0)
    return seen


def _normalize(text: str) -> str:
    return os.path.normcase(text.replace("\\", "/")).replace("\\", "/")


def find_install_processes(install_paths: Iterable[Path],
                           processes: Optional[List[ProcessInfo]] = None) -> List[ProcessInfo]:
    """Processes whose command line references any of ``install_paths``.

    The calling process and its ancestors are excluded: on CTR the deploy is
    itself launched from a shell or .bat that may sit inside the install.

    Args:
        install_paths: Install directories (the NB_INSTALL link and the slots root).
        processes: Process list to search; defaults to :func:`list_processes`.
    """
    processes = list_processes() if processes is None else processes
    excluded = _ancestors(os.getpid(), {p.pid: p.parent_pid for p in processes})
    # Match both the path as given and its resolved form: a process started
    # through a link (or macOS's /var -> /private/var) shows either.
    spellings = {spelling for path in install_paths for spelling in (str(path), os.path.realpath(path))}
    needles = [_normalize(spelling).rstrip("/") + "/" for spelling in spellings]
    return [
        process for process in processes
        if process.pid not in excluded
        and any(needle in _normalize(process.command_line) for needle in needles)
    ]
