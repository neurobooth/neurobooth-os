@ECHO OFF

:: Neurobooth folders
setx /m NB_INSTALL "C:\neurobooth-os"
setx /m NB_CONFIG "%USERPROFILE%\.neurobooth-os"

:: GUI Configs
setx /m NB_FULLSCREEN "true"

:: Sensors
setx /m MICROPHONE_NAME "BLUE USB"
setx /m FLIR_SN "20522874"

:: 

PAUSE