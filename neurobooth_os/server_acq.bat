call %NB_CONDA_INSTALL%\Scripts\activate.bat %NB_CONDA_ENV%
start /W ipython --pdb %NB_INSTALL%\neurobooth_os\server_acq.py
start /W ipython %NB_INSTALL%\extras\dump_iphone_video.py
start /W ipython %NB_INSTALL%\neurobooth_os\transfer_data.py acquisition
