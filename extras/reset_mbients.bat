call %NB_INSTALL%\.venv\Scripts\activate.bat
call python %NB_INSTALL%\extras\reset_mbients.py --json=%USERPROFILE%\mbients.json
pause
