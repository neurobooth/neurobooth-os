:: @ECHO OFF

:: Neurobooth folders
setx /m NB_INSTALL C:\neurobooth-os\
setx /m NB_CONFIG %USERPROFILE%\.neurobooth_os\
setx /m NB_CONDA %USERPROFILE%\anaconda3\envs\neurobooth-staging

:: GUI Configs
setx /m NB_FULLSCREEN "false"

:: Sensors
setx /m MICROPHONE_NAME "Yeti"
setx /m FLIR_SN "22348141"

:: Create folder for holding config files
powershell -Command "mkdir -Force %NB_CONFIG%/"

powershell -Command "cp ./neurobooth_os_config.json %NB_CONFIG%neurobooth_os_config.json"

::

:: PAUSE