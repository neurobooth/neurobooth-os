:: @ECHO OFF

:: Note: This script must be run as administrator
:: Script should be run from the folder containing this file, with the nb config files held in subdirectories
:: The subdirectories are named with the server_name of the server being configured.
:: In short, this folder structure is the same as that defined in the configs repo on github.

:: Script takes server_name as an argument.

set server_name=%1
echo %server_name%

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
start powershell -Command "mkdir -Force %NB_CONFIG%/"
:: Copy config file to config folder
start powershell -Command "cp ./%server_name%/neurobooth_os_config.json %NB_CONFIG%neurobooth_os_config.json"

::

:: PAUSE