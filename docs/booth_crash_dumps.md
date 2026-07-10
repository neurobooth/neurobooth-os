# Booth crash-dump capture & analysis

How to capture and analyze **process crashes** on the booth machines (primarily
ACQ, which owns all the flaky native device SDKs). This is the companion to the
general [logging reference](logging.md); read that first for where logs live.

There are **two distinct crash classes**, and they need **different capture
tools**. Getting this wrong wastes a downtime window, so start here.

## The text crash log (always present)

`neurobooth_os.log_manager.enable_crash_handler()` installs Python's
`faulthandler`, which writes a plain-text traceback to **`neurobooth_crash.log`**
in the log directory (see [logging.md](logging.md#where-log-files-go) — on ACQ
that is `C:\Users\ACQ\nb_os_env\neurobooth_logs`). It appends across launches
with a timestamped `--- <server> started at <time> (PID <pid>) ---` header, so
you can correlate a crash to a specific process.

**This is the first place to look**, but it only prints **Python** frames — it
cannot name the native module that actually faulted. For that you need a memory
dump (below).

## Two crash classes — capture the right way

| Class | Signature in `neurobooth_crash.log` | Reaches WER? | Capture tool |
|-------|-------------------------------------|--------------|--------------|
| **Python fatal abort (SIGABRT)** | `Fatal Python error: Aborted` | **No** | **ProcDump** |
| **Native access violation** | `Windows fatal exception: access violation` | **Yes** | **WER LocalDumps** |

- **Abort / SIGABRT** — e.g. the #710 device-finalizer teardown crash. `faulthandler`
  writes its text log and the process exits **before** `WerFault` runs, so
  **WER LocalDumps never fires** for this class. You must attach **ProcDump**
  ahead of time.
- **Native access violation (`0xC0000005`)** — e.g. the `warble.dll` Mbient
  BLE-connect crash (#824 / #674). This is a second-chance SEH exception that
  **does** reach `WerFault`, so **WER LocalDumps captures it automatically**.

## WER LocalDumps — for the access-violation class

Configured per-image under (HKLM, needs an elevated shell):

```
HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe
```

Current booth settings and how to set them:

```powershell
$k = 'HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe'
Set-ItemProperty -Path $k -Name DumpType        -Type DWord -Value 0     # custom (see note)
New-ItemProperty -Path $k -Name CustomDumpFlags -Type DWord -Value 0 -Force  # 0 = MiniDumpNormal
Set-ItemProperty -Path $k -Name DumpCount       -Type DWord -Value 10
Get-ItemProperty  $k    # confirm; DumpFolder should be ...\neurobooth_logs
```

- **`DumpType=0` + `CustomDumpFlags=0` (MiniDumpNormal)** produces a small dump —
  thread stacks + loaded-module list, a few MB — which is all `!analyze -v`
  needs to name the faulting module. **Gotcha:** on the ACQ box the documented
  `DumpType=1` ("mini") preset instead produced a **1.8 GB full-memory** dump,
  so we define the flags explicitly rather than trust the preset.
- **`DumpCount=10`** — dumps are named `python.exe.<PID>.dmp` (per-PID, so
  distinct crashes coexist) and the oldest is recycled past the cap. A restart
  cluster can otherwise evict the useful one.
- **`DumpFolder`** points at `neurobooth_logs`, alongside the text crash log.

**Keep this enabled** — it is the only *automatic* capture for the AV class. If
a future dump comes back large despite the above, something outside this key is
writing it (a `DumpType` on the parent `...\LocalDumps` key, or the app itself);
trace that before assuming the settings are wrong.

## ProcDump — for the SIGABRT / abort class

WER can't catch the abort, so attach ProcDump to the running worker and let it
catch the crash:

```powershell
winget install Microsoft.Sysinternals.ProcDump
# -ma full dump, -e on unhandled exception, -t also on process termination
procdump -accepteula -ma -e -t <PID> C:\Users\ACQ\nb_os_env\neurobooth_logs
```

Target the **child worker** process, not the launcher: on the current booth
build the `.venv` python re-launches `C:\Users\ACQ\anaconda3\python.exe` as a
child, and that child runs the device stack (see #818). Find it right after a
session starts:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select ProcessId, ParentProcessId, CommandLine
```

The one whose command line runs `server_acq.py` under `anaconda3` is the worker.

## Analyzing a dump (cdb)

WinDbg installs via `winget install Microsoft.WinDbg`, but as an **MSIX package**
its `cdb.exe` **cannot be executed in place** from the locked `WindowsApps`
folder. Copy the debugger out once:

```powershell
$wd = (Get-AppxPackage Microsoft.WinDbg).InstallLocation
robocopy "$wd\amd64" C:\dbg /E        # C:\dbg\cdb.exe is now runnable
```

Then analyze (output is a few KB — easy to attach to an issue):

```powershell
& C:\dbg\cdb.exe -z "C:\Users\ACQ\nb_os_env\neurobooth_logs\<dump>.dmp" `
    -c "!analyze -v; ~*kb; lmv; q" > analysis.txt
```

- **`!analyze -v`** — names the faulting thread and native module
  (`MODULE_NAME` / `FAULTING_MODULE`) and the failure bucket.
- **`~*kb`** — every thread's native stack (catches the real fault site even
  when `faulthandler`'s Python view showed an innocent bystander thread).
- **`lmv`** — loaded modules with versions/paths (confirms which SDK build and
  from which path — `.venv` wheel vs conda base).

If you only need a small dump from a large one (e.g. to download over a slow
link), reduce it first: `cdb -z big.dmp -c ".dump /m small.dmp; q"`.

## Worked example / issue references

The 2026-07-08 ACQ crash was diagnosed this way: `python.exe.8524.dmp` bucketed
`INVALID_POINTER_READ_c0000005_warble.dll!Unknown` at
`warble!warble_scan_result_has_service_uuid` — a native access violation in the
Mbient BLE library during connect.

- Abort / finalizer class: #710, #826
- Mbient / `warble.dll` AV class: #824, #674, #669
- Device-isolation fix that would contain both: #845
- Conda-base `.venv` (child-worker PID target): #818, [booth_venv_rebuild.md](booth_venv_rebuild.md)
