call C:\Users\ACQ\anaconda3\Scripts\activate.bat C:\Users\ACQ\anaconda3\envs\neurobooth-staging
call start /W ipython --pdb %NB_INSTALL%\neurobooth_os\server_acq.py
call start /W ipython %NB_INSTALL%\extras\dump_iphone_video.py
robocopy  /MOVE  D:\neurobooth\neurobooth_data Z:\data /e
mkdir D:\neurobooth\neurobooth_data