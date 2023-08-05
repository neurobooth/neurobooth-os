call  %NB_CONDA_INSTALL%\Scripts\activate.bat %NB_CONDA_ENV%
start /W ipython --pdb %NB_INSTALL%\neurobooth_os\gui.py
start /W ipython %NB_INSTALL%\neurobooth_os\transfer_data.py control
