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

At runtime a Windows venv always shows a **parent→child `python.exe` pair** — the ~47 KB
venv launcher (parent) spawns the base interpreter (child) as the real worker. This pair is
**normal venv-trampoline behavior, not a defect** (it is "not a dup launch" — the two entries
are one logical process). What distinguishes an *affected* machine is **which interpreter the
child is**: on an affected machine the child runs `…\anaconda3\python.exe`; on a rebuilt
machine it runs `…\AppData\Roaming\uv\python\cpython-3.8-…\python.exe`. Inspect it with:

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

Success = the `server_acq.py` **child** interpreter is the uv standalone
(`…\AppData\Roaming\uv\python\cpython-3.8-…\python.exe`) with **no `anaconda3\python.exe`
anywhere** in the list. Do **not** expect a single process — the parent→child launcher/base
pair is normal (see "How to confirm a machine is affected"); the criterion is the child's
image, not the process count.

Then watch the unclean-exit rate (`extras\perf\_investigate_silent_exit.py --audit`, needs
the Wang DB / VPN). Compare ACQ against the **GUI (`control`) box**, not STM: STM logs two
restart markers per launch, so `audit_shutdowns` deliberately excludes it and any rate you
compute for it reads 95–100% UNCLEAN regardless of health. If the ACQ rate falls toward the
GUI's, the environment was the root cause.

Pre-rebuild reference (Wang, Apr–Jul 2026, captured on #818): ACQ_0 ran **39–57% unclean**
in June–July at ~20–25 restarts/week, against a GUI control of **0–12%**. At n ≈ 22
restarts/week a real fix should show ~2 unclean per week instead of ~10 — readable after one
week, comfortable after two.

Two limits to keep in mind. `--audit` counts unclean *exits*, not aborts: it also catches
external kills, hang-and-forcequit, power loss, and logging blackouts, so a drop supports the
environment theory without proving the SIGABRT class is gone — confirm that with
`Fatal Python error: Aborted` disappearing from `neurobooth_crash.log`. And the audit targets
`Starting ACQ (index=0)` only, so ACQ_1 is not covered.

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

Per machine, **only after** its `.venv` is rebuilt off Anaconda and verified (`pyvenv.cfg`
`home` is the uv path, not `anaconda3`). Order matters — never leave a booth without a
working interpreter. Do CTR → STM → ACQ one at a time.

This procedure is the one **tested on the staging booths (TEST_CTR / TEST_STM / TEST_ACQ)
on 2026-07-16**, where the venvs were already uv-standalone and only the leftover Anaconda
installs needed removing. It replaces the earlier draft that assumed `conda` was on PATH.

### B.0 — Safety gate: is the install per-user or all-users? (do this first)

Booth machines host **two Windows accounts** — a **staging** account and an **FA Study
(production)** account — that share the physical box. This matters because:

- A **per-user** Anaconda (under `%USERPROFILE%\anaconda3`) belongs to one account only.
  Removing it from the staging account cannot affect FA Study. **Safe to proceed.**
- An **all-users** Anaconda (under `C:\ProgramData\Anaconda3`) is shared. Uninstalling it
  also pulls the base interpreter out from under the **other** account's venv. If FA Study's
  venv has not yet been verified uv-standalone, this can **brick production.** **Stop** and
  verify (and rebuild if needed) the other account's `.venv` first.

```powershell
"anaconda3 (per-user):  " + (Test-Path "$env:USERPROFILE\anaconda3")     # True = per-user
"ProgramData Anaconda:  " + (Test-Path "C:\ProgramData\Anaconda3")       # True = ALL-USERS -> STOP
Get-ChildItem HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall,
              HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall -EA SilentlyContinue |
  ForEach-Object { $_.GetValue('DisplayName') } | Where-Object { $_ -match 'Anaconda|Miniconda' }
```

Registry match under **HKCU** = per-user (safe); under **HKLM** / a `ProgramData` path =
all-users (gate on the other account). The rest of this appendix assumes **per-user**.

### B.1 — Precondition

```powershell
# home must already be the uv path, not anaconda3 (from the rebuild verify step)
Get-Content "$env:NB_INSTALL\.venv\pyvenv.cfg" | Select-String '^home'
```

### B.2 — Remove Anaconda (run the whole block in ONE shell)

`conda` is usually **not on PATH** in the service account, so call `conda.exe` by full path.
Set `$conda` and run the block together — if you set `$conda` in a different window it will
be empty here and the paths collapse to `\Scripts\conda.exe` (a "term not recognized" error).

```powershell
$conda = "$env:USERPROFILE\anaconda3"          # <- adjust if step B.0 showed miniconda3
$conda; Test-Path "$conda\Uninstall-Anaconda3.exe"   # sanity: prints the path, then True

# 1. Undo conda's shell/PATH hooks. Offline. Harmless if it errors (means no active hook).
& "$conda\Scripts\conda.exe" init --reverse --all

# 2. Official uninstaller. Local exe, no network. Drop '/S' for the GUI.
Start-Process "$conda\Uninstall-Anaconda3.exe" -ArgumentList '/S' -Wait

# 3. Delete leftovers (this does by hand what `anaconda-clean` would — see note below).
Remove-Item -Recurse -Force $conda -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:USERPROFILE\.conda","$env:USERPROFILE\.anaconda" -ErrorAction SilentlyContinue
Remove-Item -Force "$env:USERPROFILE\.condarc" -ErrorAction SilentlyContinue

# 4. Strip Anaconda entries from THIS account's User PATH.
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$cleaned  = ($userPath -split ';' | Where-Object { $_ -and $_ -notmatch 'anaconda|miniconda|conda' }) -join ';'
[Environment]::SetEnvironmentVariable('Path',$cleaned,'User')
```

> **Do not** run `conda install anaconda-clean`. It fetches from `repo.anaconda.com`, which
> the MGH network blocks (licensing). Step 3's manual deletes cover the same dotfiles.

### B.3 — Drop stale conda env vars (if present)

If this machine was set up with the old conda-based deploy, clear the vestigial variables so
they don't reintroduce a conda assumption (and remove them from `configs\deploy.bat`). These
are typically **Machine**-scope; needs an elevated shell:

```powershell
[Environment]::SetEnvironmentVariable('NB_CONDA_INSTALL', $null, 'Machine')
[Environment]::SetEnvironmentVariable('NB_CONDA_ENV',     $null, 'Machine')
```

### B.4 — Verify (open a FRESH PowerShell first)

PATH and hook changes only take effect in a new shell.

```powershell
where.exe conda        # expect: nothing found
where.exe python       # expect: NO …\anaconda3\… entry
& "$env:NB_INSTALL\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)"
# expect unchanged: …\AppData\Roaming\uv\python\cpython-3.8-…
```

**`where python` will not list the uv interpreter — that is correct, not a problem.** The
uv-managed standalone Python lives under `%APPDATA%\uv\python\…` and is intentionally not on
PATH; the venv references it directly. `where python` will only show unrelated system Pythons
(e.g. `C:\Python310`, `C:\Python27amd64`) and the Windows Store stub
(`…\WindowsApps\python.exe`). None of those is neurobooth's interpreter — the only one that
matters is the `.venv` python checked above, whose `base_prefix` must still be the uv path.

Safety notes: keep `.venv.condabak` until the machine runs clean for several sessions; on
ACQ, re-confirm `PySpin` / `pyrealsense2` / `pylsl` / `pyaudio` import from the new venv
before removing Anaconda (in case any were installed into the conda env rather than the venv).
