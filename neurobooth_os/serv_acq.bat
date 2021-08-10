call C:\Users\ACQ\anaconda3\Scripts\activate.bat C:\Users\ACQ\anaconda3\envs\neurobooth
call start /W ipython C:\neurobooth-eel\server_acq.py
robocopy  /MOV  C:\neurobooth\neurobooth_data Z:\session_data
