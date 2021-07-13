call SCHTASKS /S acq /U acq\ACQ /P 5519 /Create /TN TaskOnEvent /TR C:\neurobooth-eel\serv_acq.bat /SC ONEVENT /EC Application /MO *[System/EventID=777] /f
call SCHTASKS /S acq /U acq\ACQ /P 5519 /Run /TN "TaskOnEvent"
START /B /wait robocopy  /MOV  C:\neurobooth\neurobooth_data Z:\session_data
pause
