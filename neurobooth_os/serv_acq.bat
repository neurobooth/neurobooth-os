call C:\Users\ACQ\anaconda3\Scripts\activate.bat C:\Users\ACQ\anaconda3\envs\neurobooth
call start /W ipython --pdb C:\neurobooth-os\neurobooth_os\server_acq.py
call start /W ipython C:\neurobooth-os\dump_iphone_video.py
robocopy  /MOVE  D:\neurobooth\neurobooth_data Z:\data /e
mkdir D:\neurobooth\neurobooth_data
