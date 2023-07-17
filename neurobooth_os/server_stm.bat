call C:\Users\STM\anaconda3\Scripts\activate.bat %NB_CONDA%
start /W ipython --pdb %NB_INSTALL%\neurobooth_os\server_stm.py
call start /W ipython %NB_INSTALL%\neurobooth_os\transfer_data.py STM
