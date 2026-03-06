# Plan: Replace Anaconda with a License-Free Alternative

## Context
Anaconda's commercial licensing requires paid subscriptions for organizations above a certain size. Neurobooth-os currently uses Anaconda to manage a conda environment with 58 conda packages and 101 pip packages (Python 3.8.18). Most application dependencies are already installed via pip; conda is primarily used for:
- Environment/Python version management
- A handful of binary packages: `portaudio`, `pyaudio`, `numpy` (MKL-linked), and system-level libraries
- Activation scripts in `.bat` files (`%NB_CONDA_INSTALL%\Scripts\activate.bat`)

## Options Evaluated

### 1. Miniforge (Recommended - easiest migration)
- **What**: Community-maintained conda installer using only `conda-forge` channel (no Anaconda defaults)
- **License**: BSD-3, fully free for commercial use
- **Migration effort**: Minimal — drop-in replacement for Anaconda. Same `conda` CLI, same `environment.yml` format, same `activate.bat` pattern
- **Pros**: Keeps entire existing workflow intact. `environment.yml` works as-is (already uses conda-forge). All bat scripts just need path updates from `anaconda3` to `miniforge3`
- **Cons**: Still uses conda (slower solver, though `mamba` is included). Doesn't modernize the tooling

### 2. uv (Most modern, fastest)
- **What**: Rust-based Python package/project manager by Astral (makers of ruff). Manages Python versions, virtual environments, and pip installs — all in one tool
- **License**: MIT/Apache-2.0, fully free
- **Migration effort**: Medium — requires converting `environment.yml` to `requirements.txt` or `pyproject.toml`. Need to verify all 101 pip packages + find pip equivalents for conda-only packages
- **Pros**: Extremely fast (10-100x faster than pip). Built-in Python version management (`uv python install 3.11`). Lock files for reproducibility. Active development, growing ecosystem. Replaces conda, pip, venv, and pyenv in one tool
- **Cons**: Newer tool (v1.0 released 2024). No conda-forge access — packages like `pyaudio` and `portaudio` need Windows wheels or build tools. More migration work upfront

### 3. pixi (Modern conda-forge frontend)
- **What**: Fast, modern package manager built on conda-forge (by the prefix.dev team)
- **License**: BSD-3, fully free
- **Migration effort**: Medium — new `pixi.toml` format, but understands conda-forge packages
- **Pros**: Fast (Rust-based). Access to conda-forge for binary packages. Lock files built-in. Can mix conda and pip dependencies
- **Cons**: Relatively new. Different CLI and project structure. Less community adoption than uv

## Recommendation: Miniforge now, uv later

### Phase 1 — Miniforge (immediate, low-risk)
Replace Anaconda with Miniforge on all machines. This is a 1-day change:

1. **Install Miniforge** on each machine (installs to `%USERPROFILE%\miniforge3`)
2. **Update environment variables** in `deploy.bat` (both repos):
   - `NB_CONDA_INSTALL` → `%USERPROFILE%\miniforge3`
   - `NB_CONDA_ENV` → `%USERPROFILE%\miniforge3\envs\neurobooth-staging`
3. **Update hardcoded paths** in:
   - `extras/reset_mbients.bat`
   - `tests/deployment-test/run_timing_tests.bat`
4. **Remove `defaults` channel** from `environment_staging.yml` (keep only `conda-forge`)
5. **Recreate environment**: `conda env create -f environment_staging.yml`
6. **Uninstall Anaconda**

No Python code changes. No dependency changes. Existing `environment.yml` works as-is.

### Phase 2 — Modernize (future, when ready)
Once stable on Miniforge, consider migrating to `uv` for faster installs and modern tooling:

1. Upgrade Python from 3.8 (EOL) to 3.11+
2. Convert `environment.yml` to `pyproject.toml` with all deps
3. Replace conda-only packages with pip equivalents (e.g., `pyaudio` wheels exist for Python 3.11+)
4. Replace `activate.bat` pattern with `uv run` in server bat files
5. Drop MKL in favor of OpenBLAS numpy (simpler, no Intel dependency)

### Files to modify (Phase 1 only)

| File | Change |
|------|--------|
| `configs/deploy.bat` | Update `NB_CONDA_INSTALL` and `NB_CONDA_ENV` paths |
| `neurobooth-os/examples/configs/deploy.bat` | Same path updates |
| `neurobooth-os/examples/set_conda_env.bat` | Same path updates |
| `neurobooth-os/neurobooth_os/install.bat` | Same path updates |
| `neurobooth-os/environment_staging.yml` | Remove `defaults` channel |
| `neurobooth-os/extras/reset_mbients.bat` | Update hardcoded anaconda3 path |
| `neurobooth-os/tests/deployment-test/run_timing_tests.bat` | Update hardcoded anaconda3 path |

### Note on Python 3.8
Python 3.8 reached end-of-life in October 2024. Upgrading to 3.11+ is strongly recommended regardless of which tool is chosen. This is a separate effort but should be planned soon.
