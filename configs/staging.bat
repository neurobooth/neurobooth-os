@ECHO OFF

:: Neurobooth folders
setx /m setx NB_INSTALL "C:/neurobooth-os" /m
setx /m setx NB_CONFIG "$HOME/.neurobooth-os" /m

:: GUI Configs
setx /m NB_FULLSCREEN "false"

:: Sensors
setx /m MICROPHONE_NAME "Yeti"
setx /m FLIR_SN "22348141"

:: 

PAUSE