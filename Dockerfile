FROM continuumio/miniconda3:4.12.0

# Install everything locally for now
# Install jupyter lab for server
RUN conda install jupyterlab

# Install local in editable mode
RUN pip install -e .
