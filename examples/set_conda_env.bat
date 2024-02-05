REM run in conda prompt in project root
echo on
call conda deactivate
pause
call conda env remove --name neurobooth-staging
pause
call conda env create --file environment_staging.yml
pause
call conda activate neurobooth-staging
call pip install -e .
call pip install --index-url=https://pypi.sr-support.com sr-research-pylink
call pip install c:\spinnaker\spinnaker_python-3.1.0.79-cp38-cp38-win_amd64.whl
pause
call conda remove hdf5
pip uninstall h5py
pip uninstall h5io
pip install h5py==3.7.0
pip install h5io
:: call pip install --user --force-reinstall h5py==3.7.0