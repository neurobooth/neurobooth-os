# Removing Anaconda from the booth machines

## Status and background

The booth venvs were originally built on the **Anaconda base interpreter** instead of a
uv-managed standalone Python, which made `.venv\Scripts\python.exe` a copy of conda's
interpreter that re-launched `…\anaconda3\python.exe` as the real worker. That was the
suspected contributor to the ACQ `SIGABRT` investigated in #818 and #710 / #824.

**All booth venvs — Wang, Merrimac, and CTRU, every role — were rebuilt on a uv-managed
standalone Python as of 2026-07-17.** The interpreter is now pinned by `.python-version`
(`3.8`) at the repo root, so `uv sync` cannot silently adopt Anaconda again, and
`configs\deploy.bat` no longer sets the vestigial `NB_CONDA_*` variables. The rebuild
runbook that this document used to carry has been removed — for a new machine, follow the
install steps in the top-level `README.md`.

**One step remains:** uninstalling Anaconda itself, which is still present on the booths
even though nothing points at it. Removal at **Wang** is deliberately gated on a week of
production sessions running clean with no environment-related issues.

The procedure below is the one **tested on the staging booths (TEST_CTR / TEST_STM /
TEST_ACQ) on 2026-07-16**. Do one machine at a time, CTR → STM → ACQ — never leave a booth
without a working interpreter.

## B.0 — Safety gate: is the install per-user or all-users? (do this first)

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
all-users (gate on the other account). The rest of this procedure assumes **per-user**.

## B.1 — Precondition

```powershell
# home must be the uv path, not anaconda3
Get-Content "$env:NB_INSTALL\.venv\pyvenv.cfg" | Select-String '^home'
```

## B.2 — Remove Anaconda (run the whole block in ONE shell)

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

## B.3 — Drop stale conda env vars (if present)

`configs\deploy.bat` no longer writes these, but machines deployed before that change still
carry them. They are usually **Machine**-scope, but `setx` without `/m` writes **User**
scope, so check both — a leftover User-scope copy would survive a Machine-only cleanup and
still shadow it for that account. Run in an **elevated** shell (Machine scope requires it):

```powershell
# Show where each one currently lives, before changing anything.
foreach ($v in 'NB_CONDA_INSTALL','NB_CONDA_ENV') {
  foreach ($s in 'Machine','User') {
    "{0,-17} {1,-8} [{2}]" -f $v, $s, [Environment]::GetEnvironmentVariable($v, $s)
  }
}

# Remove from both scopes. Passing $null deletes the variable outright
# (it does NOT set it to an empty string). Harmless if it was never set.
foreach ($v in 'NB_CONDA_INSTALL','NB_CONDA_ENV') {
  foreach ($s in 'Machine','User') {
    [Environment]::SetEnvironmentVariable($v, $null, $s)
  }
}
```

Verify in a **fresh** shell — removals do not apply to already-open sessions:

```powershell
foreach ($v in 'NB_CONDA_INSTALL','NB_CONDA_ENV') {
  foreach ($s in 'Machine','User') {
    "{0,-17} {1,-8} {2}" -f $v, $s,
      $(if ($null -eq [Environment]::GetEnvironmentVariable($v, $s)) { 'gone' } else { 'STILL SET' })
  }
}
```

All four lines should read `gone`.

## B.4 — Verify (open a FRESH PowerShell first)

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

Safety notes: if a machine still has a `.venv.condabak` backup, keep it until that machine
runs clean for several sessions. On ACQ, re-confirm `PySpin` / `pyrealsense2` / `pylsl` /
`pyaudio` import from the venv before removing Anaconda (in case any were installed into the
conda env rather than the venv).

Once Anaconda is removed everywhere and Wang has run clean, this document can be deleted —
update the link in [booth_crash_dumps.md](booth_crash_dumps.md) at the same time.
