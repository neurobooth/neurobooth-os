@ECHO OFF

:: Note: This script must be run as administrator

:: Note: Script should be run from the root of the config repo folder root.
:: It copies the nb config files held in 'shared' and in the environment-specific subdirectory.
:: The environment-specific source subdirectories are named for the environment (e.g. 'staging')
:: The destination subdirectories are defined by the environment variable NB_CONFIG.

:: Note: Script takes the environment name as an argument. It should be lowercase to match the folder name
:: e.g. 'staging'

set env_name=%1
echo Environment name is %env_name%

:: Set Neurobooth folder locations as environment variables
setx /m NB_INSTALL C:\neurobooth-os\
setx /m NB_CONFIG %USERPROFILE%\.neurobooth_os\

:: Set Anaconda folder locations as environment variables
setx /m NB_CONDA_INSTALL %USERPROFILE%\anaconda3
start setx /m NB_CONDA_ENV %NB_CONDA_INSTALL%\envs\neurobooth-staging

:: Create folder for holding config files
start powershell -Command "mkdir -Force %NB_CONFIG%/"

:: Copy shared files to config folder
start powershell -Command "robocopy /s .\shared\ $ENV:NB_CONFIG"

:: Copy environment-specific files (e.g. neurobooth_os_config.json) to config folders
start powershell -Command "robocopy /s .\environments\%env_name%\ %NB_CONFIG%\"
::

PAUSE
