call SCHTASKS /Create /TN TaskOnEvent /TR C:\neurobooth\neurobooth-eel\server_stm.bat /SC ONEVENT /EC Application /MO *[System/EventID=777] /f
call SCHTASKS /Run /TN "TaskOnEvent"	