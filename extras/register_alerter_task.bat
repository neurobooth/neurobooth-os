@echo off
REM Registers the booth alerter (neurobooth_os.alerting) to run every minute as the
REM current Windows user, on the CTR machine. Run it once from the CTR account of each
REM environment; staging and production share machines, so the task name includes the
REM account. Re-running replaces the existing task.
REM
REM pythonw.exe runs without a console window, so nothing flashes on the CTR screen.
REM /IT runs the task only while this user is logged on, which needs no stored password.
REM Task Scheduler does not start a run while the previous one is still going.

if "%NB_INSTALL%"=="" (
    echo NB_INSTALL is not set; run this from a configured CTR account.
    exit /b 1
)

schtasks /Create /F /TN "neurobooth-alerter-%USERNAME%" /SC MINUTE /MO 1 /IT ^
    /TR "\"%NB_INSTALL%\.venv\Scripts\pythonw.exe\" -m neurobooth_os.alerting run"
