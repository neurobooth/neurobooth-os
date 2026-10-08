# Neurobooth-os

Neurobooth-os is a python package to initialize, synchronize and record
behavioral and physiological data streams from wearables, D-/RGB cameras, eye
tracker, ECG, mouse and microphone in a booth.

## Installation

Dependencies are managed with [uv](https://docs.astral.sh/uv/). Install uv
once (no admin needed):

```powershell
winget install astral-sh.uv
```

or:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then, from the repo root:

```powershell
git clone https://github.com/neurobooth/neurobooth-os.git
cd neurobooth-os
uv sync
```

This creates a `.venv` with Python 3.8 and every pinned dependency from
`uv.lock`. To verify:

```powershell
uv run python -c "import neurobooth_os"
```

should print nothing and exit cleanly.

### Per-machine extras

Run these **after** `uv sync`.

**STM** — EyeLink eye tracker:

```powershell
uv sync --extra eyelink
```

The `eyelink` extra installs `sr-research-pylink` from PyPI. SR Research's own
index stays configured in `pyproject.toml` as an explicit index: uv uses it
only for packages pinned to it under `[tool.uv.sources]`. If the install
fails, fall back to the manual installer:

* Create an SR Research support account
* Download the `EyeLink Developers Kit v2.1.1 (32 and 64 bit)` installer
* Install the EyeLink Developers Kit
* `cd "C:\Program Files (x86)\SR Research\EyeLink\SampleExperiments\Python"`
* `uv run python install_pylink.py`

**ACQ** — FLIR Spinnaker SDK (proprietary, distributed as a local wheel):

* Download the Spinnaker SDK from https://www.flir.com/products/spinnaker-sdk/
* Extract the `.whl` and install into the venv:

```powershell
uv pip install spinnaker_python-3.x.x.x-cp38-cp38-win_amd64.whl
```

**CTR** — LabRecorder v1.17.1 swap (workaround for [#812][i812] / [#813][i813]):

`liesl` ships a LabRecorderCLI built against `liblsl 1.13-b4` (2019), but
the producers on STM/ACQ produce LSL traffic with `pylsl 1.16.2` (2022).
The 3-year wire-protocol gap segfaults the recorder at XDF finalize and
truncates the resulting files. We override the bundled binaries with
upstream v1.17.1 (`liblsl 1.17.5`). The vendored binaries live in
`vendor/labrecorder-v1.17.1/`. Apply (or re-apply, after every `uv sync`):

```powershell
powershell.exe -ExecutionPolicy Bypass `
    -File "%NB_INSTALL%\extras\perf\upgrade_labrecorder_v1.17.1.ps1"
```

The script is idempotent: it detects pristine / half-applied / already-applied
states, SHA-256 verifies at every hop, and only modifies the venv when needed.
Add `-DryRun` to preview without changes.

[i812]: https://github.com/neurobooth/neurobooth-os/issues/812
[i813]: https://github.com/neurobooth/neurobooth-os/issues/813

### Operator environment variables

The runtime batch scripts (`server_*.bat`, `transfer_data.bat`, etc.) expect
`NB_INSTALL` to point at the repo root, and use `%NB_INSTALL%\.venv\Scripts\activate.bat`
to activate the uv-managed environment.

Set `NB_INSTALL` system-wide (Settings → Environment Variables) to the repo root —
on the booths that is `%USERPROFILE%\nb_os_env\neurobooth-os`. The legacy
`NB_CONDA_INSTALL` and `NB_CONDA_ENV` variables are no longer set or read by
anything; delete them if they are still present on a machine.

> **Deploying updates:** once a booth is set up as above, update all three
> machines of an environment with one command on its CTR machine —
> `%NB_INSTALL%\nb_deploy.bat`. It checks out both repos, syncs each venv with
> that machine's extras, and switches over blue-green so `nb_deploy rollback`
> undoes it in seconds. See [docs/deployment.md](docs/deployment.md).
>
> The older per-machine chain in the `configs` repo
> (`checkout_and_deploy.bat` → `github_checkout.bat` → `deploy.bat` → `version.bat`)
> still exists but does not sync the venv, and must not be used on a machine
> that `nb_deploy` has switched to the blue-green layout (it would write into
> the live slot directly).

## Setup

Neurobooth runs on multiple Windows server machines, which communicate via WMI. See the [inter-machine setup runbook](https://github.com/neurobooth/neurobooth-os/blob/master/docs/inter_machine_setup.md) for configuration details.

Neurobooth requires a PostgreSQL database. Connection is established with
`neurobooth_os.iout.metadator.get_conn()`. Per `~/.neurobooth_os_secrets`,
the local IP is `192.168.100.1`; remote connections go to
`neurodoor.nmr.mgh.harvard.edu` using the private key at `~/.ssh/id_rsa`.

To set up an SSH key, first activate the partner VPN, then run:

```powershell
ssh-keygen
ssh-copy-id userID@neurodoor.nmr.mgh.harvard.edu
```

For the configuration data, see
[docs/system_configuration.md](https://github.com/neurobooth/neurobooth-os/blob/master/docs/system_configuration.md).

## Run

Neurobooth runs on three computers; the entry point is `gui.py` on CTR.

* **CTR** (control): hosts the GUI and relays commands to the other
  computers to start recording from the Neurobooth devices and present
  stimuli. The lab recorder software runs here.
* **STM** (stimulus): runs the tasks using `psychopy`.
* **ACQ** (acquisition): acquires data.

Each computer has a server that listens for messages from the other
computers. CTR and STM also communicate with the database.
