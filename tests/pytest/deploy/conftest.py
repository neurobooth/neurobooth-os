"""Fixtures for the deploy tests.

These tests need only the standard library, pytest, PyYAML and pydantic —
not the booth venv — so they run on macOS and Linux as well as Windows::

    uv run --no-project --with pytest --with pyyaml --with pydantic \\
        python -m pytest tests/pytest/deploy -o addopts=""
"""

from pathlib import Path

import pytest
from simulated_booth import GIT_IDENTITY, SimulatedBooth


@pytest.fixture
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in GIT_IDENTITY.items():
        monkeypatch.setenv(key, value)
    # Keep the developer's own git config (signing, hooks, default branch) out of the simulation.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(Path(__file__).with_name("empty.gitconfig")))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def booth(tmp_path: Path, git_identity: None) -> SimulatedBooth:
    """A staging booth in today's (pre-blue-green) layout, checked out at origin's current heads."""
    simulated = SimulatedBooth(tmp_path)
    simulated.install_legacy()
    return simulated
