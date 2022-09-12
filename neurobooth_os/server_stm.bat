call C:\Users\STM\anaconda3\Scripts\activate.bat C:\Users\STM\anaconda3\envs\neurobooth-staging
start /W ipython --pdb C:\neurobooth-os\neurobooth_os\server_stm.py
robocopy  /MOVE  C:\neurobooth\neurobooth_data Z:\data /e
mkdir C:\neurobooth\neurobooth_data