call C:\Users\STM\anaconda3\Scripts\activate.bat C:\Users\STM\anaconda3\envs\eyelink
start /W ipython -i C:\neurobooth-eel\neurobooth_os\server_stm.py
robocopy  /MOVE  C:\neurobooth\neurobooth_data Z:\session_data /e
mkdir C:\neurobooth\neurobooth_data