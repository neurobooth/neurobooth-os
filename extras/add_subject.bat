call %NB_CONDA_INSTALL%\Scripts\activate.bat %NB_CONDA_ENV%
start /W ipython --pdb %NB_INSTALL%\extras\add_subject.py
