@echo off
REM Install / refresh the neurobooth-os environment using uv.
REM
REM Prerequisite: uv on PATH. Install with:
REM     winget install astral-sh.uv
REM   or:
REM     powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
REM
REM Per-machine extras (run AFTER `uv sync`):
REM   STM:  uv sync --extra eyelink
REM   ACQ:  uv pip install <path>\spinnaker_python-3.x.x.x-cp38-cp38-win_amd64.whl

setlocal
cd /d "%~dp0\.."

where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: uv is not on PATH. Install it with one of:
    echo   winget install astral-sh.uv
    echo   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    exit /b 1
)

uv sync
