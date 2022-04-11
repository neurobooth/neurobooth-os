call C:\Users\ACQ\anaconda3\Scripts\activate.bat C:\Users\ACQ\anaconda3\envs\neurobooth_new
call start /W ipython C:\neurobooth-eel\neurobooth_os\server_acq.py
robocopy  /MOVE  D:\neurobooth\neurobooth_data Z:\data /e
mkdir D:\neurobooth\neurobooth_data