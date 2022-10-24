<<<<<<< Updated upstream
FROM continuumio/miniconda3:4.12.0

# Install everything locally for now
# Install jupyter lab for server
RUN conda install jupyterlab
=======
FROM python:3.9.13-windowsservercore-1809

# Install everything locally for now
# Install jupyter lab for server
RUN pip install jupyterlab
>>>>>>> Stashed changes

# Install local in editable mode
RUN pip install -e .
