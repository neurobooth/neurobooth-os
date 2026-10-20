@echo off
:: Deploys a neurobooth-os release TAG to every machine (CTR, STM, ACQ) of this
:: booth environment. Run it from the neurobooth-os repo root on any of them:
::
::   deploy_all.bat v1.2.3
::
:: See neurobooth_os\deploy_all.py for what it needs. The command is one
:: parenthesized block because the local deploy checks out TAG, which can
:: rewrite this file while cmd.exe is still reading it. A block is parsed in
:: full before it runs. "(goto) 2>nul" leaves the batch file without reading it
:: again, so there is no "The batch file cannot be found." when TAG doesn't
:: contain this file, and exit /b still returns python's exit code.
setlocal
set "PYTHONPATH=%~dp0."
(
    "%~dp0.venv\Scripts\python.exe" -m neurobooth_os.deploy_all neurobooth-os "%~dp0." %*
    (goto) 2>nul & exit /b
)
