REM run in conda prompt in project root
echo on
conda deactivate
conda env remove --name neurobooth-staging
conda env create --file environment_staging.yml
pip install -e .
pip install --index-url=https://pypi.sr-support.com sr-research-pylink
pip install c:\spinnaker\spinnaker_python-3.1.0.79-cp38-cp38-win_amd64.whl
pip install --user --force-reinstall h5py-3.10.0-cp312-cp312-win_amd64.whl