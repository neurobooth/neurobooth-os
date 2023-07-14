@ECHO OFF

:: Neurobooth folders
setx /m NB_INSTALL C:\neurobooth-os\
setx /m NB_CONFIG %USERPROFILE%\.neurobooth_os\
setx /m NB_ACQ_CONDA C:\Users\ACQ\anaconda3\envs\neurobooth-staging
setx /m NB_STM_CONDA C:\Users\STM\anaconda3\envs\neurobooth-staging
setx /m NB_ACQ_DATA D:\neurobooth\neurobooth_data

:: GUI Configs
setx /m NB_FULLSCREEN "true"

:: Sensors
setx /m MICROPHONE_NAME "BLUE USB"
setx /m FLIR_SN "20522874"

:: Create folder for holding config files
powershell -Command "mkdir -Force %NB_CONFIG%/"

powershell -Command "cp ./neurobooth_os_config.json %NB_CONFIG%neurobooth_os_config.json"

:: 

PAUSE