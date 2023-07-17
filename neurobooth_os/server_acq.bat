call C:\Users\ACQ\anaconda3\Scripts\activate.bat %NB_CONDA%
call start /W ipython --pdb %NB_INSTALL%\neurobooth_os\server_acq.py
call start /W ipython %NB_INSTALL%\extras\dump_iphone_video.py
call start /W ipython %NB_INSTALL%\neurobooth_os\transfer_data.py ACQ
