@ECHO OFF

:: Neurobooth folders
setx /m NB_INSTALL C:\neurobooth\
setx /m NB_CONFIG %USERPROFILE%\.neurobooth_os\
setx /m NB_ACQ_CONDA C:\Users\ACQ\anaconda3\envs\neurobooth-staging
setx /m NB_STM_CONDA C:\Users\STM\anaconda3\envs\neurobooth-staging
setx /m NB_ACQ_DATA D:\neurobooth\neurobooth_data

:: GUI Configs
setx /m NB_FULLSCREEN "true"

:: Sensors
setx /m MICROPHONE_NAME "BLUE USB"
setx /m FLIR_SN "20522874"

:: 

PAUSE