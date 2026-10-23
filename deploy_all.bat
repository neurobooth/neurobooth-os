@echo off
:: Deploys a neurobooth-os release TAG to every machine (CTR, STM, ACQ) of this
:: booth environment. Run it from the neurobooth-os repo root on any of them:
::
::   deploy_all.bat v1.2.3
::
:: See neurobooth_os\deploy_all.py for what it needs.

:: Variables set below vanish when the script ends, so the caller's shell is
:: left unchanged.
setlocal

:: %~dp0 is the folder this .bat is in: the repo root. Python then imports
:: neurobooth_os from this repo.
set "PYTHONPATH=%~dp0."

:: Everything below is one parenthesized block. cmd.exe normally reads a .bat
:: one line at a time while running it, and the local deploy checks out TAG,
:: which can rewrite or delete this file partway through. A block is read in
:: full before it runs, so that change can't confuse it.
(
    rem Run the repo's own venv Python on neurobooth_os.deploy_all, passing which
    rem repo this is, the repo folder, and whatever was typed after deploy_all.bat
    rem (%%* - the TAG).
    "%~dp0.venv\Scripts\python.exe" -m neurobooth_os.deploy_all neurobooth-os "%~dp0." %*

    rem "(goto) 2>nul" leaves this script without cmd.exe reading the file again,
    rem so there is no "The batch file cannot be found." when TAG doesn't contain
    rem this file. exit /b then passes on python's exit code (0 = success).
    (goto) 2>nul & exit /b
)
