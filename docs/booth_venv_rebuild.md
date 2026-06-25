# Booth uv environment rebuild — removing the Anaconda interpreter dependency

## When to use this

Use this runbook when a booth's `.venv` is built on the **Anaconda base interpreter**
instead of a uv-managed standalone Python. The symptom that surfaced it: an ACQ
server launches **two** `python.exe` (a venv launcher that re-spawns the Anaconda
base interpreter as a child), and crash dumps show the standard library loading
from `…\anaconda3\lib\` while third-party packages load from `…\.venv\…`.

Background and the crash investigation this came out of: #818 (root cause),
#710 / #824 (the ACQ `SIGABRT` this environment is a suspected contributor to).

## How to confirm a machine is affected

In the relevant service account (`CTR` / `STM` / `ACQ`):

```powershell
Get-Content "$env:NB_INSTALL\.venv\pyvenv.cfg"
& "$env:NB_INSTALL\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)"
(Get-Item "$env:NB_INSTALL\.venv\Scripts\python.exe").Length
```

Affected if:

- `pyvenv.cfg` `home` (and `sys.base_prefix`) point into `anaconda3` (or `miniconda3`), and/or
- `python.exe` is ~500 KB (a copy of the conda interpreter) rather than ~47 KB (the uv launcher).

At runtime an affected ACQ also shows a parent→child `python.exe` pair — the venv
launcher and a child `…\anaconda3\python.exe`, both running `server_acq.py`:

```powershell
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
```

## Why it happens (root cause)

The conda → uv migration (#632 / #758) moved dependency management to uv but built
the booth venvs **on top of the existing Anaconda CPython** rather than a standalone
interpreter. There is no `.python-version` in the repo, so when `uv sync` / `uv venv`
ran during the upgrade it adopted whatever `python` was first on PATH — Anaconda —
and pinned the venv's `home` to it. Because the seed is a conda interpreter,
`.venv\Scripts\python.exe` is a *copy* of conda's `python.exe`, which re-launches the
canonical `…\anaconda3\python.exe` as a child; that child is the real worker. The fix
is to rebuild the venv on a uv-managed standalone Python so the interpreter is
isolated and single-process.

The project targets **Python 3.8** (cp38-only wheel pins throughout `pyproject.toml`,
e.g. `blosc2<2.0.1`), so the rebuild target is **3.8.20** (a uv-managed standalone
build), not a newer Python. Moving off 3.8 is tracked in #682.

## Is conda required anywhere in the deploy path?

No — verified against the configs deploy chain:

- `configs\checkout_and_deploy.bat` calls only `github_checkout.bat` (git checkout),
  `deploy.bat`, and `version.bat`. **None create or activate a conda env.**
- `configs\deploy.bat` sets `NB_INSTALL=%USERPROFILE%\nb_os_env\neurobooth-os` (correct —
  it matches where `.venv` and `neurobooth_os\` live) and then robocopies config files.
  It also still *sets* the vestigial `NB_CONDA_INSTALL` / `NB_CONDA_ENV` variables, but
  nothing in the chain uses them.

So nothing *requires* conda except the venv's own `home` pin (and Anaconda being the
default `python` on PATH when the venv was built). `NB_INSTALL` is **not** misconfigured.

> The README "Upgrading from a conda-based booth" section currently claims the deploy
> chain calls `conda env create`. That note is stale — the scripts above do not. See
> Prevention.

## Runbook — rebuild (ACQ worked example)

Do this in a maintenance window (no patient sessions). Keep the old `.venv` as a backup
until verified; every step before "Appendix B — removing Anaconda" is reversible.

### 1. Stop services and capture state

On **CTR**, close the GUI (so it stops relaunching ACQ). Then on **ACQ** (elevated PowerShell):

```powershell
cd $env:NB_INSTALL

# stop the ACQ python processes; disable any relaunching scheduled task for now
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Where-Object { $_.CommandLine -like '*server_acq.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-ScheduledTask | Where-Object { $_.TaskName -like '*acq*' -or $_.TaskName -like '*neurobooth*' }
# Disable-ScheduledTask -TaskName "<the ACQ task>"

# record the current package set and interpreter binding
& "$env:NB_INSTALL\.venv\Scripts\python.exe" -m pip freeze > "$env:USERPROFILE\pre_rebuild_freeze.txt"
Get-Content "$env:NB_INSTALL\.venv\pyvenv.cfg"

# locate the FLIR/Spinnaker wheel — it is NOT in uv.lock and must be reinstalled by hand
Get-ChildItem C:\ -Recurse -Filter "spinnaker_python-*cp38*win_amd64.whl" -ErrorAction SilentlyContinue |
  Select-Object FullName

# back up the old venv (rename, don't delete)
Rename-Item "$env:NB_INSTALL\.venv" ".venv.condabak"
```

If the spinnaker wheel can't be found, stop and locate it (or re-download the matching
`cp38` wheel from FLIR) before continuing — it is the one dependency `uv sync` will not
restore.

### 2. Rebuild on a uv-managed standalone 3.8

```powershell
cd $env:NB_INSTALL
uv --version
uv python install 3.8                 # uv-managed standalone CPython (resolves to 3.8.20)
uv venv --python 3.8 .venv            # explicit --python defeats the PATH/anaconda problem
uv sync                               # deps from uv.lock
uv pip install "<path>\spinnaker_python-<ver>-cp38-cp38-win_amd64.whl"   # ACQ only
```

Per-machine extras (from the README upgrade runbook): **STM** also `uv sync --extra eyelink`;
**CTR** also re-apply `extras\perf\upgrade_labrecorder_v1.17.1.ps1` after every `uv sync`
(#812 / #813).

> Offline booth: `uv python install` needs internet. If the machine can't reach it,
> install python.org **3.8.10** (the last 3.8 with a Windows installer) via your software
> channel and use `uv venv --python "C:\path\to\python3.8\python.exe" .venv`. The
> requirement is simply a non-Anaconda 3.8.

### 3. Verify the rebuild

```powershell
Get-Content "$env:NB_INSTALL\.venv\pyvenv.cfg"                  # home now …\uv\python\cpython-3.8.20…, NOT anaconda3
(Get-Item "$env:NB_INSTALL\.venv\Scripts\python.exe").Length   # ~47 KB
& "$env:NB_INSTALL\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)"
& "$env:NB_INSTALL\.venv\Scripts\python.exe" -c "import neurobooth_os; import PySpin, pyrealsense2, pylsl, pyaudio; print('imports OK')"
```

### 4. Verify the launch

Re-enable the ACQ task (or let the GUI start ACQ), start a session, and confirm:

```powershell
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
```

Success = exactly one `server_acq.py` process, image = the `.venv` python, no child
`anaconda3\python.exe`. Then watch the unclean-exit rate
(`extras\perf\_investigate_silent_exit.py --audit`, needs the Wang DB / VPN); if it falls
toward the STM box's, the environment was the root cause.

### Rollback

```powershell
Remove-Item "$env:NB_INSTALL\.venv" -Recurse -Force
Rename-Item "$env:NB_INSTALL\.venv.condabak" ".venv"
```

Once a few sessions run clean, delete the backup:
`Remove-Item "$env:NB_INSTALL\.venv.condabak" -Recurse -Force`.

## Prevention

- Pin the interpreter so `uv` can't silently adopt Anaconda again: add a `.python-version`
  (`3.8`) at the repo root (or `uv python pin 3.8`) and commit it.
- Remove `NB_CONDA_INSTALL` / `NB_CONDA_ENV` from `configs\deploy.bat`, and fix the stale
  README "deploy chain note."

## Appendix A — checking the other machines

Assume every booth is affected until checked (the same `uv sync` runbook was applied
uniformly). Roles: **CTR, STM, ACQ_0, ACQ_1** at each site (Wang, Merrimac, CTRU). On
each, in its service account, run the three commands in "How to confirm a machine is
affected" above. Fix each affected machine with the rebuild runbook (with that machine's
extras).

## Appendix B — safely removing Anaconda

Per machine, **only after** its `.venv` is rebuilt off Anaconda and verified. Order
matters — never leave a booth without a working interpreter. Do CTR → STM → ACQ one at a
time.

```powershell
# 1. precondition: home must be the uv path, not anaconda3
Get-Content "$env:NB_INSTALL\.venv\pyvenv.cfg"
conda env list

# 2. remove the old neurobooth conda env
conda env remove -n neurobooth-staging

# 3. stop conda auto-activating in future shells
conda init --reverse cmd.exe powershell

# 4. drop the stale env vars (and remove them from configs\deploy.bat so they don't return)
[Environment]::SetEnvironmentVariable('NB_CONDA_INSTALL', $null, 'Machine')
[Environment]::SetEnvironmentVariable('NB_CONDA_ENV',     $null, 'Machine')

# 5. reboot, then confirm anaconda is no longer the default python and the launch still works
where.exe python      # should NOT list …\anaconda3\…

# 6. uninstall Anaconda and clear residue
& "$env:USERPROFILE\anaconda3\Uninstall-Anaconda3.exe"
Remove-Item "$env:USERPROFILE\anaconda3","$env:USERPROFILE\.conda","$env:USERPROFILE\.condarc","$env:USERPROFILE\.anaconda" -Recurse -Force -ErrorAction SilentlyContinue

# 7. scrub remaining anaconda entries from System + User PATH
#    (…\anaconda3, …\anaconda3\Scripts, …\anaconda3\Library\bin, …\anaconda3\condabin),
#    then reboot and re-verify the launch.
```

Safety notes: keep `.venv.condabak` until the machine runs clean for several sessions;
on ACQ, re-confirm `PySpin` / `pyrealsense2` / `pylsl` / `pyaudio` import from the new
venv before removing Anaconda (in case any were installed into the conda env rather than
the venv).
