@ECHO OFF

:: Neurobooth folders
setx /m NB_INSTALL "C:/neurobooth-os"
setx /m NB_CONFIG "$HOME/.neurobooth-os"

:: GUI Configs
setx /m NB_FULLSCREEN "false"

:: Sensors
setx /m MICROPHONE_NAME "Yeti"
setx /m FLIR_SN "22348141"

:: 

PAUSE