"""Thin git wrappers used by the deploy agent and orchestrator.

Standard library only (see the package docstring).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class GitError(Exception):
    """A git command failed."""


def git(repo: Path, *args: str) -> str:
    """Run ``git -C repo args`` and return stripped stdout.

    Raises:
        GitError: git exited non-zero; the message carries git's stderr.
    """
    completed = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise GitError(f"git {' '.join(args)} (in {repo}) failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def head_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def origin_url(repo: Path) -> str:
    return git(repo, "remote", "get-url", "origin")


def has_tracked_changes(repo: Path) -> bool:
    """True if tracked files are modified. Untracked files (e.g. secrets.yaml) are ignored."""
    return bool(git(repo, "status", "--porcelain", "--untracked-files=no"))


def fetch(repo: Path) -> None:
    git(repo, "fetch", "--force", "--tags", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*")


def has_commit(repo: Path, sha: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, check=False,
    )
    return completed.returncode == 0


def checkout_detached(repo: Path, sha: str) -> None:
    """Check out ``sha`` detached, discarding edits to tracked files.

    Only used on trees the deploy owns (slot checkouts) or has already
    verified are clean (the configs checkout).
    """
    git(repo, "checkout", "--force", "--detach", sha)


@dataclass(frozen=True)
class ResolvedRef:
    """A user-supplied ref pinned to the commit every machine will deploy."""

    ref: str
    sha: str
    kind: str  # "branch", "tag" or "commit"

    @property
    def label(self) -> str:
        """Version string stamped into the install: the tag itself, else ``ref@sha7``."""
        if self.kind == "tag":
            return self.ref
        if self.kind == "commit":
            return self.sha[:12]
        return f"{self.ref}@{self.sha[:7]}"


def default_branch(repo: Path) -> str:
    """Name of origin's default branch (``master`` for neurobooth-os, ``main`` for configs)."""
    output = git(repo, "ls-remote", "--symref", "origin", "HEAD")
    for line in output.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split("\t")[0][len("ref: refs/heads/"):]
    raise GitError(f"Could not determine origin's default branch for {repo}")


def resolve_remote_ref(repo: Path, ref: str) -> ResolvedRef:
    """Resolve a branch, tag or full commit SHA against origin.

    Branches win over tags of the same name, matching git's own lookup order
    for ``refs/heads`` before ``refs/tags``.

    Raises:
        GitError: The ref does not exist on origin.
    """
    if _FULL_SHA.match(ref):
        return ResolvedRef(ref=ref, sha=ref, kind="commit")
    listing: List[List[str]] = [
        line.split("\t") for line in git(repo, "ls-remote", "origin").splitlines() if "\t" in line
    ]
    refs = {name: sha for sha, name in listing}
    if f"refs/heads/{ref}" in refs:
        return ResolvedRef(ref=ref, sha=refs[f"refs/heads/{ref}"], kind="branch")
    # Annotated tags list the tag object and, with ^{}, the commit it points to.
    if f"refs/tags/{ref}^{{}}" in refs:
        return ResolvedRef(ref=ref, sha=refs[f"refs/tags/{ref}^{{}}"], kind="tag")
    if f"refs/tags/{ref}" in refs:
        return ResolvedRef(ref=ref, sha=refs[f"refs/tags/{ref}"], kind="tag")
    raise GitError(f"'{ref}' is not a branch or tag on origin of {repo}")
