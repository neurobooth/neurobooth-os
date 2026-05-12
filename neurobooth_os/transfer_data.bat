call %NB_INSTALL%\.venv\Scripts\activate.bat
start /W python %NB_INSTALL%\extras\dump_iphone_video.py
start /W python %NB_INSTALL%\neurobooth_os\transfer_data.py
