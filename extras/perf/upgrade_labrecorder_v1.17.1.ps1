#requires -Version 5.1
# Swap liesl-bundled LabRecorderCLI.exe + liblsl64.dll for the upstream
# LabRecorder v1.17.1 build (which ships liblsl v1.17.5 under the filename
# lsl.dll). Targets the uv-managed booth env at %NB_INSTALL%\.venv.
#
# Filed against #812 -- LabRecorderCLI segfaults at XDF finalize due to a
# 3-year liblsl version gap between producers (pylsl 1.16.2) and the
# bundled consumer (1.13-b4). See the issue for full root-cause analysis.
#
# IMPORTANT: the old liesl-bundled LabRecorderCLI was linked against a
# DLL named liblsl64.dll; the new upstream LabRecorderCLI is linked
# against lsl.dll. The swap therefore RENAMES the DLL filename, not just
# its content. Post-swap state:
#   <libDir>\LabRecorderCLI.exe                 (v1.17.1)
#   <libDir>\lsl.dll                            (v1.17.5)
#   <libDir>\liblsl64.dll.v1.13-b4.bak.<stamp>  (renamed-aside backup)
#   <libDir>\LabRecorderCLI.exe.v1.13-b4.bak.<stamp>
#
# Pre-flight:
#   - Stop the neurobooth GUI on the booth (close the GUI window so no
#     LabRecorderCLI subprocess is in flight).
#
# Run (downloads the zip from GitHub by default):
#   powershell.exe -ExecutionPolicy Bypass -File .\upgrade_labrecorder_v1.17.1.ps1
#
# To use a pre-staged zip instead of downloading, pass -ZipPath <path>.
# Add -DryRun to see what would happen without modifying anything.
#
# Expected SHA-256 of the upstream zip (verified before extraction):
#   LabRecorder-1.17.0-Win_amd64.zip  01BDE1D9AF07D29DE1A8363C967CC1EEAF524915F2DB76552484F7BECDB161ED
#
# Expected SHA-256 of files in the zip after extraction (post-swap targets):
#   LabRecorderCLI.exe  5A838787C938BE19E90A8092C0DA436EC7C01DFF917B50285EE96B5A851820C5
#   lsl.dll             6C97D5456D498EF6A062C74C54FF87CD39EFD58DCF67D7BEA4B01263D50DF445
#
# Expected SHA-256 of the files this script will REPLACE (pre-swap):
#   LabRecorderCLI.exe  2EA0025F21D4D77BD7A0E311D01F9E65B590883F750EA5103628F334943778A1
#   liblsl64.dll        AF991B79B8857506D28E2CF621CC4956A9513FFBEC795531D6C12AEA5250CEF4

[CmdletBinding()]
param(
    [string]$ZipPath,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# ---- download config ----
$DOWNLOAD_URL = 'https://github.com/labstreaminglayer/App-LabRecorder/releases/download/v1.17.1/LabRecorder-1.17.0-Win_amd64.zip'
$EXPECTED_ZIP = '01BDE1D9AF07D29DE1A8363C967CC1EEAF524915F2DB76552484F7BECDB161ED'

# ---- expected hashes (all upper-case) ----
$EXPECTED_OLD_CLI = '2EA0025F21D4D77BD7A0E311D01F9E65B590883F750EA5103628F334943778A1'
$EXPECTED_OLD_DLL = 'AF991B79B8857506D28E2CF621CC4956A9513FFBEC795531D6C12AEA5250CEF4'
$EXPECTED_NEW_CLI = '5A838787C938BE19E90A8092C0DA436EC7C01DFF917B50285EE96B5A851820C5'
$EXPECTED_NEW_DLL = '6C97D5456D498EF6A062C74C54FF87CD39EFD58DCF67D7BEA4B01263D50DF445'

function Get-Sha256 {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToUpper()
}

function Write-Step { Write-Host ""; Write-Host "==> $args" -ForegroundColor Cyan }
function Write-Ok   { Write-Host "    OK: $args" -ForegroundColor Green }
function Write-Warn { Write-Host "    WARN: $args" -ForegroundColor Yellow }
function Write-Err  { Write-Host "    ERROR: $args" -ForegroundColor Red }

Write-Host ""
Write-Host "================================================================"
Write-Host " LabRecorder v1.17.1 binary swap (issue #812)"
Write-Host "================================================================"
Write-Host "machine:    $env:COMPUTERNAME"
Write-Host "user:       $env:USERNAME"
Write-Host "date:       $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Write-Host "NB_INSTALL: $env:NB_INSTALL"
Write-Host "ZipPath:    $ZipPath"
Write-Host "DryRun:     $($DryRun.IsPresent)"
Write-Host ""

# ---- step 1: validate environment ----
Write-Step "Validating environment"

if (-not $env:NB_INSTALL) {
    Write-Err "NB_INSTALL is not set on this machine (see README.md install runbook)."
    exit 1
}
$libDir = Join-Path $env:NB_INSTALL '.venv\Lib\site-packages\liesl\files\labrecorder\lib'
if (-not (Test-Path $libDir)) {
    Write-Err "liesl lib dir not found: $libDir"
    exit 1
}
$cliPath    = Join-Path $libDir 'LabRecorderCLI.exe'
$liblslPath = Join-Path $libDir 'liblsl64.dll'   # old name liesl historically used
$lslPath    = Join-Path $libDir 'lsl.dll'        # new name upstream LabRecorder uses
if (-not (Test-Path $cliPath)) { Write-Err "missing: $cliPath"; exit 1 }
Write-Ok "liesl lib dir present: $libDir"

# ---- step 2: check no LabRecorderCLI / GUI is running ----
Write-Step "Checking that no LabRecorderCLI / neurobooth GUI is running"
$running = Get-Process -Name 'LabRecorderCLI' -ErrorAction SilentlyContinue
if ($running) {
    Write-Err "LabRecorderCLI is currently running (PID(s): $($running.Id -join ', '))."
    Write-Err "Close the neurobooth GUI and wait for any in-flight recording to finalize before retrying."
    exit 1
}
Write-Ok "no LabRecorderCLI processes detected"

# ---- step 3: hash current binaries, classify state ----
Write-Step "Hashing current binaries"
$curCli    = Get-Sha256 $cliPath
$curLiblsl = Get-Sha256 $liblslPath
$curLsl    = Get-Sha256 $lslPath
Write-Host "    current LabRecorderCLI.exe: $curCli"
Write-Host "    current liblsl64.dll:        $(if ($curLiblsl) { $curLiblsl } else { '(absent)' })"
Write-Host "    current lsl.dll:             $(if ($curLsl) { $curLsl } else { '(absent)' })"

# State A -- pristine: old CLI + old liblsl64.dll, no lsl.dll
$statePristine = ($curCli -eq $EXPECTED_OLD_CLI -and $curLiblsl -eq $EXPECTED_OLD_DLL -and -not $curLsl)
# State B -- already correctly applied: new CLI + new lsl.dll (liblsl64.dll status irrelevant)
$stateApplied = ($curCli -eq $EXPECTED_NEW_CLI -and $curLsl -eq $EXPECTED_NEW_DLL)
# State C -- half-applied (older buggy version of this script): new CLI + new content in liblsl64.dll name + no lsl.dll
$stateHalfApplied = ($curCli -eq $EXPECTED_NEW_CLI -and $curLiblsl -eq $EXPECTED_NEW_DLL -and -not $curLsl)

if ($stateApplied) {
    Write-Ok "binaries already at v1.17.1 -- nothing to do"
    if ($curLiblsl -eq $EXPECTED_NEW_DLL) {
        Write-Warn "stray liblsl64.dll (v1.17.5 content) is present alongside lsl.dll."
        Write-Warn "  it is harmless leftover from the older buggy swap script;"
        Write-Warn "  remove it manually if you want a clean directory:"
        Write-Warn "    Remove-Item '$liblslPath'"
    } elseif ($curLiblsl -eq $EXPECTED_OLD_DLL) {
        Write-Warn "old v1.13-b4 liblsl64.dll is still present alongside the new lsl.dll."
        Write-Warn "  it is harmless leftover (new CLI loads lsl.dll, ignores liblsl64.dll);"
        Write-Warn "  consider renaming it aside:"
        Write-Warn "    Move-Item '$liblslPath' '$($liblslPath).v1.13-b4.bak'"
    }
    exit 0
}

if ($stateHalfApplied) {
    Write-Step "Detected half-applied state from older buggy script version"
    Write-Host "    LabRecorderCLI.exe is the new v1.17.1, but the DLL is named"
    Write-Host "    liblsl64.dll (old name) instead of lsl.dll (the name the new"
    Write-Host "    CLI looks for). Fix: rename in place."
    if ($DryRun) {
        Write-Host ""
        Write-Host "==> DRY RUN: would rename '$liblslPath' -> '$lslPath'"
        exit 0
    }
    Copy-Item -Path $liblslPath -Destination $lslPath -Force
    # Keep liblsl64.dll around as harmless leftover; the new CLI won't load it.
    $check = Get-Sha256 $lslPath
    if ($check -ne $EXPECTED_NEW_DLL) {
        Write-Err "post-rename hash mismatch for lsl.dll (got $check)"
        Remove-Item -Path $lslPath -Force
        exit 1
    }
    Write-Ok "renamed liblsl64.dll -> lsl.dll (new CLI will now load it)"
    Write-Host ""
    Write-Host "================================================================"
    Write-Host " DONE. Restart the neurobooth GUI; the next recording uses the"
    Write-Host " new binaries."
    Write-Host "================================================================"
    exit 0
}

if (-not $statePristine) {
    Write-Warn "current state does not match any known transition path:"
    Write-Warn "  expected pristine (old CLI + old liblsl64.dll + no lsl.dll), OR"
    Write-Warn "  expected applied  (new CLI + new lsl.dll), OR"
    Write-Warn "  expected half-applied (new CLI + new content as liblsl64.dll + no lsl.dll)."
    Write-Warn "Re-deploy from the documented baseline, then re-run."
    exit 1
}
Write-Ok "current binaries match pristine v1.13-b4 state -- proceeding with full swap"

# ---- step 4: get the zip (download or use staged) ----
if (-not $ZipPath) {
    Write-Step "Downloading upstream LabRecorder v1.17.1 zip"
    $ZipPath = Join-Path $env:TEMP 'LabRecorder-1.17.0-Win_amd64.zip'
    if (Test-Path $ZipPath) {
        $cached = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToUpper()
        if ($cached -eq $EXPECTED_ZIP) {
            Write-Ok "found valid cached zip: $ZipPath"
        } else {
            Write-Warn "cached zip at $ZipPath has wrong hash ($cached); redownloading"
            Remove-Item -Path $ZipPath -Force
        }
    }
    if (-not (Test-Path $ZipPath)) {
        Write-Host "    url: $DOWNLOAD_URL"
        Write-Host "    -->  $ZipPath"
        try {
            # PS 5.1: -UseBasicParsing avoids IE engine dependency on machines
            # without Internet Explorer initial setup completed.
            Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $ZipPath -UseBasicParsing
        } catch {
            Write-Err "download failed: $_"
            Write-Err "If the booth has no internet, stage the zip manually and re-run with -ZipPath <path>."
            exit 1
        }
        Write-Ok "downloaded: $ZipPath"
    }
}
if (-not (Test-Path $ZipPath)) { Write-Err "zip not found: $ZipPath"; exit 1 }
Write-Step "Verifying zip SHA-256"
$zipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToUpper()
Write-Host "    zip SHA-256: $zipHash"
if ($zipHash -ne $EXPECTED_ZIP) {
    Write-Err "zip hash mismatch."
    Write-Err "  expected: $EXPECTED_ZIP"
    Write-Err "  got:      $zipHash"
    Write-Err "Refusing to proceed -- the zip is corrupt or tampered with."
    exit 1
}
Write-Ok "zip hash matches expected v1.17.1"

# ---- step 5: extract upstream binaries from zip ----
Write-Step "Extracting LabRecorderCLI.exe and lsl.dll from the upstream zip"
$tempDir = Join-Path $env:TEMP "lr_swap_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $tempDir | Out-Null
try {
    Expand-Archive -Path $ZipPath -DestinationPath $tempDir -Force
    # Use Where-Object instead of -Filter: the latter goes through the
    # Win32 FindFirstFile filter syntax which has quirks across PS 5.1
    # builds (case sensitivity, 8.3 short names, etc.).
    $extracted = Get-ChildItem -Path $tempDir -Recurse -File
    $newCli = $extracted | Where-Object { $_.Name -ieq 'LabRecorderCLI.exe' } | Select-Object -First 1
    $newDll = $extracted | Where-Object { $_.Name -ieq 'lsl.dll' }            | Select-Object -First 1
    if (-not $newCli -or -not $newDll) {
        Write-Err "did not find both LabRecorderCLI.exe and lsl.dll in the zip"
        Write-Err "extracted tree under $tempDir`:"
        foreach ($f in $extracted) { Write-Host "    $($f.FullName)" }
        exit 1
    }

    Write-Step "Verifying SHA-256 of extracted binaries against expected v1.17.1 values"
    $extCli = Get-Sha256 $newCli.FullName
    $extDll = Get-Sha256 $newDll.FullName
    Write-Host "    extracted LabRecorderCLI.exe: $extCli"
    Write-Host "    extracted lsl.dll:             $extDll"
    if ($extCli -ne $EXPECTED_NEW_CLI) {
        Write-Err "extracted LabRecorderCLI.exe hash mismatch."
        Write-Err "  expected: $EXPECTED_NEW_CLI"
        Write-Err "  got:      $extCli"
        exit 1
    }
    if ($extDll -ne $EXPECTED_NEW_DLL) {
        Write-Err "extracted lsl.dll hash mismatch."
        Write-Err "  expected: $EXPECTED_NEW_DLL"
        Write-Err "  got:      $extDll"
        exit 1
    }
    Write-Ok "both extracted binaries hash-match the documented v1.17.1 values"

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $cliBackup    = "${cliPath}.v1.13-b4.bak.$stamp"
    $liblslBackup = "${liblslPath}.v1.13-b4.bak.$stamp"

    if ($DryRun) {
        Write-Host ""
        Write-Host "==> DRY RUN: would back up and swap the binaries here."
        Write-Host "    backup target:  $cliBackup"
        Write-Host "    rename-aside:   $liblslPath -> $liblslBackup"
        Write-Host "    new CLI:        $($newCli.FullName) -> $cliPath"
        Write-Host "    new DLL:        $($newDll.FullName) -> $lslPath"
        exit 0
    }

    # ---- step 6: back up + swap ----
    Write-Step "Backing up current binaries"
    Copy-Item -Path $cliPath    -Destination $cliBackup
    # Move the old liblsl64.dll out of the way completely (not just copy):
    # the new CLI does not look for liblsl64.dll, so leaving it in place
    # would just be dead weight + potential confusion if anything else
    # ever resolves DLLs by that legacy name.
    Move-Item -Path $liblslPath -Destination $liblslBackup
    Write-Ok "backups written:"
    Write-Host "        $cliBackup"
    Write-Host "        $liblslBackup    (renamed aside from $liblslPath)"

    Write-Step "Swapping in v1.17.1 binaries"
    Copy-Item -Path $newCli.FullName -Destination $cliPath -Force
    Copy-Item -Path $newDll.FullName -Destination $lslPath -Force

    # ---- step 7: post-swap verification ----
    Write-Step "Verifying post-swap hashes"
    $postCli = Get-Sha256 $cliPath
    $postLsl = Get-Sha256 $lslPath
    Write-Host "    post-swap LabRecorderCLI.exe: $postCli"
    Write-Host "    post-swap lsl.dll:             $postLsl"

    $ok = $true
    if ($postCli -ne $EXPECTED_NEW_CLI) {
        Write-Err "post-swap LabRecorderCLI.exe hash mismatch -- rolling back"
        $ok = $false
    }
    if ($postLsl -ne $EXPECTED_NEW_DLL) {
        Write-Err "post-swap lsl.dll hash mismatch -- rolling back"
        $ok = $false
    }
    if (-not $ok) {
        Copy-Item -Path $cliBackup    -Destination $cliPath -Force
        Move-Item -Path $liblslBackup -Destination $liblslPath -Force
        if (Test-Path $lslPath) { Remove-Item -Path $lslPath -Force }
        Write-Err "rolled back from backups"
        exit 1
    }
    Write-Ok "post-swap hashes confirmed"

    Write-Host ""
    Write-Host "================================================================"
    Write-Host " DONE. Restart the neurobooth GUI; the next recording uses the"
    Write-Host " new binaries. Watch log_application for further"
    Write-Host " 'LabRecorderCLI exited with code 3221225477' rows -- they"
    Write-Host " should stop appearing."
    Write-Host ""
    Write-Host " To roll back manually:"
    Write-Host "   Copy-Item '$cliBackup'    '$cliPath'    -Force"
    Write-Host "   Move-Item '$liblslBackup' '$liblslPath' -Force"
    Write-Host "   Remove-Item '$lslPath'"
    Write-Host "================================================================"
    Write-Host ""
} finally {
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
