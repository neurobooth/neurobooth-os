call  C:\Users\CTR\anaconda3\Scripts\activate.bat C:\Users\CTR\anaconda3\envs\neurobooth
call start/W ipython --pdb C:\neurobooth-os\neurobooth_os\gui.py False mock_neurobooth_1
robocopy  /MOVE  C:\neurobooth\neurobooth_data Z:\data /e
mkdir C:\neurobooth\neurobooth_data 