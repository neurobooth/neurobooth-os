call %NB_INSTALL%\.venv\Scripts\activate.bat
call start /W ipython %NB_INSTALL%\extras\dump_iphone_video.py
robocopy  /MOVE  D:\neurobooth\neurobooth_data Z:\data /e
mkdir D:\neurobooth\neurobooth_data
