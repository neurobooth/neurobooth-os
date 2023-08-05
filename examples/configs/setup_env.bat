:: @ECHO OFF

:: Neurobooth folders
setx /m NB_INSTALL C:\neurobooth-os\
setx /m NB_CONFIG %USERPROFILE%\.neurobooth_os\
:: Anaconda folders
setx /m NB_CONDA_INSTALL %USERPROFILE%\anaconda3
call setx /m NB_CONDA_ENV %NB_CONDA_INSTALL%\envs\neurobooth-staging

:: GUI Configs
setx /m NB_FULLSCREEN "false"

:: Sensors
setx /m MICROPHONE_NAME "Yeti"
setx /m FLIR_SN "22348141"

:: Create folder for holding config files
powershell -Command "mkdir -Force %NB_CONFIG%/"
:: Copy config file to config folder
powershell -Command "cp ./neurobooth_os_config.json %NB_CONFIG%neurobooth_os_config.json"

::

:: PAUSE