Neurobooth-os
-------------

Neurobooth-os is a python package to initialize, synchronize and record
behavioral and physiological data streams from wearables, D-/RGB cameras, eye tracker,
ECG, mouse and microphone in a booth.

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

It requires a postgreSQL database running on a server. Currently, as specified in 
`~/.neurobooth_os_secrets` the local IP is 192.168.100.1, and remotely it connects to 
`neurodoor.nmr.mgh.harvard.edu` using the private key in '~/.ssh/id_rsa' as specified in
`neurobooth_os.iout.metadator`.

To setup a private key, first activate the VPN (partner's virtual private network), then run in
the terminal: 
```
ssh-keygen
ssh-copy-id userID@neurodoor.nmr.mgh.harvard.edu
```

Next, set up secrets and configuration files. In a python session, run:
```
    import neurobooth_os.secrets_info
    import neurobooth_os.config
```
This will generate `~/.neurobooth_os_secrets` and `~/.neurobooth_os_config`.
Edit them with your info and path to folders. 


Run
----

The program runs on 3 different computers and the starting point is
``gui.py``. The computers are:

* CTR (control) computer: This computer hosts the GUI and relays commands
to the other computers to start recording from the Neurobooth devices
and presenting stimuli. The lab recorder software is on this computer.

* STM (stimulus) computer: This computer runs the tasks using ``psychopy``.

* ACQ (acquisition) computer: This computer acquires data.

Each computer has a server that listens for communication from the other
computers in the form of string messages. CTR and STM computer communicate
with the database.
