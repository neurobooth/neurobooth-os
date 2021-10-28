call C:\Users\ACQ\anaconda3\Scripts\activate.bat C:\Users\ACQ\anaconda3\envs\neurobooth
call start /W ipython -i C:\neurobooth-eel\neurobooth_os\server_acq.py
robocopy  /MOVE  C:\neurobooth\neurobooth_data Z:\session_data /e
mkdir C:\neurobooth\neurobooth_data