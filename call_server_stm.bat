call SCHTASKS /S 192.168.1.8 /U STM /P 551955 /Create /TN TaskOnEvent /TR C:\neurobooth\neurobooth-eel\server_stm.bat /SC ONEVENT /EC Application /MO *[System/EventID=777] /f
call SCHTASKS /S 192.168.1.8 /U STM /P 551955 /Run /TN "TaskOnEvent"	
pause