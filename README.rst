Neurobooth-os
-------------

Neurobooth-os is a python package to initialize, synchronize and record
behavioral and physiological data streams in a Neurobooth.

Installations
-------------

We recommend the Anaconda Python distribution. To install neurobooth-os, simply do:

$ pip install -e git+https://github.com/neurobooth/neurobooth-os.git#egg=neurobooth_os

and it will install neurobooth-os along with the dependencies which are not already installed.

To check if everything worked fine, you can do:

$ python -c 'import neurobooth_os'

and it should not give any error messages.

Setup
-----

The program runs on 3 different computers and the starting point is
``gui.py``. The computers are:

* CTR (control) computer: This computer hosts the GUI and relays commands
to the other computers to start recording from the Neurobooth devices
and presenting stimuli. The lab recorder software is on this computer.

* STM (stimuli) computer: This computer runs the tasks using ``psychopy``.

* ACQ (acquisition) computer: This computer acquires data.

Each computer has a server that listens for communication from the other
computers in the form of string messages. CTR and STM computer communicate
with the database.
