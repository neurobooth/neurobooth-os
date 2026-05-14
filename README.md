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

The `eyelink` extra installs `sr-research-pylink` from the SR Research custom
index (configured in `pyproject.toml`). If that fails, fall back to the
manual installer:

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

### Operator environment variables

The runtime batch scripts (`server_*.bat`, `transfer_data.bat`, etc.) expect
`NB_INSTALL` to point at the repo root, and use `%NB_INSTALL%\.venv\Scripts\activate.bat`
to activate the uv-managed environment.

Set `NB_INSTALL` system-wide (Settings → Environment Variables) to e.g.
`C:\neurobooth-os`. The legacy `NB_CONDA_INSTALL` and `NB_CONDA_ENV` variables
are no longer used and can be removed.

## Upgrading from a conda-based booth

For machines that were running the conda-based environment
(`environment_staging.yml`, `neurobooth-staging`), follow this runbook on
each booth (CTR → STM → ACQ):

1. **Stop running services** — close the GUI, stop any running
   `server_acq.py` / `server_stm.py` processes, ensure no XDF jobs are mid-run.

2. **Pull the new code** from master once this PR is merged:

   ```powershell
   cd %NB_INSTALL%
   git pull
   ```

3. **Install uv** if not already on PATH:

   ```powershell
   winget install astral-sh.uv
   ```

   Open a new shell so PATH picks up `uv.exe`.

4. **Build the new venv:**

   ```powershell
   uv sync
   ```

   On STM also run:

   ```powershell
   uv sync --extra eyelink
   ```

   On ACQ also run:

   ```powershell
   uv pip install <path>\spinnaker_python-3.x.x.x-cp38-cp38-win_amd64.whl
   ```

5. **Update operator environment variables** (Settings → Environment
   Variables → System):
   * Remove `NB_CONDA_INSTALL` and `NB_CONDA_ENV` — no longer used.
   * Confirm `NB_INSTALL` is set and points at the repo root.

6. **Smoke-test:** open a new shell and run

   ```powershell
   %NB_INSTALL%\.venv\Scripts\activate.bat
   python -c "import neurobooth_os"
   ```

   It should exit cleanly with no output.

7. **Optional cleanup** — once you're confident the uv env works, the old
   conda environment can be removed:

   ```powershell
   conda env remove -n neurobooth-staging
   ```

   (and uninstall Anaconda/Miniconda entirely if the booth has no other use
   for it.)

> **Deploy chain note:** `configs/checkout_and_deploy.bat` and `configs/version.bat` (in the separate `configs` repo) call `conda env create --file environment_staging.yml`. They must be updated to
> call `uv sync` instead **before** running them against this branch, or staging deploy will fail. Coordinate that change with this PR's merge.

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
