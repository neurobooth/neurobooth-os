call %NB_CONDA_INSTALL%\Scripts\activate.bat %NB_CONDA_ENV%
start /W ipython --pdb %NB_INSTALL%\neurobooth_os\server_acq.py
