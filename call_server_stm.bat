call SCHTASKS /S stm /U stm\STM /P 5519 /Create /TN TaskOnEvent /TR C:\neurobooth-eel\server_stm.bat /SC ONEVENT /EC Application /MO *[System/EventID=777] /f
call SCHTASKS /S stm /U stm\STM /P 5519 /Run /TN "TaskOnEvent"	
START /B /wait robocopy  /MOV  C:\neurobooth\neurobooth_data Z:\session_data
pause