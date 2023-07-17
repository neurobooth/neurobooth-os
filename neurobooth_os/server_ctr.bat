call  C:\Users\CTR\anaconda3\Scripts\activate.bat %NB_CONDA%
call start/W ipython --pdb %NB_INSTALL%\neurobooth_os\gui.py
call start /W ipython %NB_INSTALL%\neurobooth_os\transfer_data.py CTR
