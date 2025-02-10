call  %NB_CONDA_INSTALL%\Scripts\activate.bat %NB_CONDA_ENV%
start /W ipython %NB_INSTALL%\extras\create_flir_videos.py
start /W ipython %NB_INSTALL%\extras\dump_iphone_video.py
start /W ipython %NB_INSTALL%\neurobooth_os\transfer_data.py
