call %NB_INSTALL%\.venv\Scripts\activate.bat
call python %NB_INSTALL%\extras\sync_subject_table.py --source-creds=%NB_INSTALL%\extras\perf\db_credentials.merrimac.json %*
exit /b %ERRORLEVEL%
