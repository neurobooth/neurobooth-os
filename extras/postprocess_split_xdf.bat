call  %NB_CONDA_INSTALL%\Scripts\activate.bat %NB_CONDA_ENV%
call start /W ipython %NB_INSTALL%\extras\run_xdf_split_postproces.py
