call C:\Users\ACQ\anaconda3\Scripts\activate.bat %NB_CONDA%
start /W ipython --pdb %NB_INSTALL%\neurobooth_os\server_acq.py
start /W ipython %NB_INSTALL%\extras\dump_iphone_video.py
start /W ipython %NB_INSTALL%\neurobooth_os\transfer_data.py ACQ
