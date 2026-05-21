#requires -Version 5.1
# Report the path, size, SHA-256, and embedded git version string of every
# liblsl binary in the booth's neurobooth-os install -- both the pylsl-
# bundled lsl.dll (producer/consumer-side liblsl used by Python) and the
# liesl-bundled liblsl64.dll + LabRecorderCLI.exe (consumer-side, only on
# CTR normally).
#
# Filed for the #812 investigation into LabRecorderCLI segfaults at XDF
# finalize. Run on STM, ACQ, and CTR; paste the output back so we can
# compare across machines and confirm whether any liblsl version drift
# exists between producers and the recorder.
#
# Looks up files relative to %NB_INSTALL%\.venv per the install runbook in
# README.md (sections "Operator environment variables" and "Upgrading from
# a conda-based booth").
#
# Two ways to run:
#   1. Paste the entire file contents into a PowerShell window and press Enter.
#   2. Save as a file and run:
#        powershell.exe -ExecutionPolicy Bypass -File <path>\check_liblsl_versions.ps1

$ErrorActionPreference = 'Continue'

function Get-LslVersionString {
    # liblsl embeds its version as an ASCII string of the form
    # "git:vX.YZ/branch:.../build:Release/compiler:...". Extract it without
    # having to LoadLibrary the DLL (which would require matching bitness
    # and would side-effect this process).
    param([string]$DllPath)
    try {
        $bytes = [System.IO.File]::ReadAllBytes($DllPath)
        $ascii = [System.Text.Encoding]::ASCII.GetString($bytes)
        $m = [regex]::Match($ascii, 'git:[A-Za-z0-9./_:-]{4,200}/build:[A-Za-z]+')
        if ($m.Success) { return $m.Value }
        return '(no git:... version string found in DLL)'
    } catch {
        return "(error reading DLL: $_)"
    }
}

function Show-File {
    param([string]$Label, [string]$Path, [switch]$WithLslVersion)
    Write-Host "[$Label]"
    if (-not (Test-Path $Path)) {
        Write-Host "  path:    $Path"
        Write-Host "  status:  NOT FOUND"
        Write-Host ""
        return
    }
    $f = Get-Item $Path
    Write-Host "  path:    $($f.FullName)"
    Write-Host "  size:    $($f.Length)"
    Write-Host "  sha256:  $((Get-FileHash $f.FullName -Algorithm SHA256).Hash)"
    if ($WithLslVersion) {
        Write-Host "  version: $(Get-LslVersionString $f.FullName)"
    }
    Write-Host ""
}

Write-Host ""
Write-Host "===== neurobooth liblsl diagnostic ====="
Write-Host "machine:    $env:COMPUTERNAME"
Write-Host "user:       $env:USERNAME"
Write-Host "date:       $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Write-Host "psver:      $($PSVersionTable.PSVersion)"
Write-Host "NB_INSTALL: $env:NB_INSTALL"
Write-Host ""

if (-not $env:NB_INSTALL) {
    Write-Host "ERROR: NB_INSTALL is not set on this machine."
    Write-Host "Per README.md the install runbook requires NB_INSTALL pointing at the"
    Write-Host "neurobooth-os repo root. Fix the env var (Settings -> Environment"
    Write-Host "Variables -> System) and re-run."
    exit 1
}

$venv = Join-Path $env:NB_INSTALL '.venv'
if (-not (Test-Path $venv)) {
    Write-Host "ERROR: '$venv' does not exist."
    Write-Host "NB_INSTALL is set but the .venv created by 'uv sync' is missing."
    exit 1
}

$pylslDll  = Join-Path $venv 'Lib\site-packages\pylsl\lib\lsl.dll'
$lieslDll  = Join-Path $venv 'Lib\site-packages\liesl\files\labrecorder\lib\liblsl64.dll'
$lieslExe  = Join-Path $venv 'Lib\site-packages\liesl\files\labrecorder\lib\LabRecorderCLI.exe'

Show-File 'pylsl/lib/lsl.dll'              $pylslDll -WithLslVersion
Show-File 'liesl/.../liblsl64.dll'         $lieslDll -WithLslVersion
Show-File 'liesl/.../LabRecorderCLI.exe'   $lieslExe

Write-Host '===== end ====='
Write-Host ''
