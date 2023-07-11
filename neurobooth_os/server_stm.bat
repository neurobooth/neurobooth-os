call C:\Users\STM\anaconda3\Scripts\activate.bat %NB_STM_CONDA%
start /W ipython --pdb %NB_INSTALL%\neurobooth_os\server_stm.py
robocopy  /MOVE  %NB_INSTALL%\neurobooth_data Z:\data /e
mkdir %NB_INSTALL%\neurobooth_data