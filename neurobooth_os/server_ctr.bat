call  C:\Users\CTR\anaconda3\Scripts\activate.bat C:\Users\CTR\anaconda3\envs\neurobooth-staging
call start/W ipython --pdb %NB_INSTALL%\neurobooth_os\gui.py
robocopy  /MOVE  %NB_INSTALL%\neurobooth_data Z:\data /e
mkdir %NB_INSTALL%\neurobooth_data
