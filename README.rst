Neurobooth-os
-------------

Neurobooth-os is a python package to initialize, synchronize and record
behavioral and physiological data streams from wearables, D-/RGB cameras, eye tracker,
ECG, mouse and microphone in a booth.

Installations
-------------

Dependencies are managed with `uv <https://docs.astral.sh/uv/>`_. Install uv
once (no admin needed)::

    winget install astral-sh.uv

or::

    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

Then, from the repo root::

    git clone https://github.com/neurobooth/neurobooth-os.git
    cd neurobooth-os
    uv sync

This creates a `.venv` with Python 3.8 and every pinned dependency from
`uv.lock`. To verify::

    uv run python -c "import neurobooth_os"

should print nothing and exit cleanly.

Per-machine extras (run AFTER `uv sync`):

**STM** -- EyeLink eye tracker::

    uv sync --extra eyelink

The `eyelink` extra installs `sr-research-pylink` from the SR Research
custom index (configured in `pyproject.toml`). If that fails, fall back to
the manual installer:

* Create an SR Research support account
* Download the `EyeLink Developers Kit v2.1.1 (32 and 64 bit)` installer
* Install the EyeLink Developers Kit
* `cd "C:\Program Files (x86)\SR Research\EyeLink\SampleExperiments\Python"`
* `uv run python install_pylink.py`

**ACQ** -- FLIR Spinnaker SDK (proprietary, distributed as a local wheel):

* Download the Spinnaker SDK from https://www.flir.com/products/spinnaker-sdk/
* Extract the `.whl` and install into the venv::

    uv pip install spinnaker_python-3.x.x.x-cp38-cp38-win_amd64.whl


Setup
-----
As described below, Neurobooth is designed to run on multiple Windows server machines. To do this, it requires that 
you setup your servers to communicate via WMI. Please see the documentation (https://github.com/neurobooth/neurobooth-os/blob/master/docs/enable_WMI_instuctions.txt), which explains how to configure WMI for more information. 

Neurobooth requires a postgreSQL database running on a server. Connection is established with the function
`neurobooth_os.iout.metadator.get_conn()`. Currently, as specified in 
`~/.neurobooth_os_secrets` the local IP is 192.168.100.1, and remotely it connects to 
`neurodoor.nmr.mgh.harvard.edu` using the private key in '~/.ssh/id_rsa'.

To setup a private key, first activate the VPN (partner's virtual private network), then run in
the terminal::

$ ssh-keygen
$ ssh-copy-id userID@neurodoor.nmr.mgh.harvard.edu


Next, set up the configuration data. Please see the instructions at:
https://github.com/neurobooth/neurobooth-os/blob/master/docs/system_configuration.md


Run
----

As mentioned above, Neurobooth runs on 3 different computers and the starting point is
``gui.py``. The computers are:

* CTR (control) computer: This computer hosts the GUI and relays commands
to the other computers to start recording from the Neurobooth devices
and presenting stimuli. The lab recorder software is on this computer.

* STM (stimulus) computer: This computer runs the tasks using ``psychopy``.

* ACQ (acquisition) computer: This computer acquires data.

Each computer has a server that listens for communication from the other
computers in the form of string messages. CTR and STM computer communicate
with the database.
