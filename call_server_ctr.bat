call SCHTASKS /Create /TN TaskOnEvent /TR C:\Users\neurobooth\Desktop\neurobooth\software\neurobooth-eel\server_ctr.bat /SC ONEVENT /EC Application /MO *[System/EventID=777] /f
call SCHTASKS /Run /TN "TaskOnEvent"	
pause