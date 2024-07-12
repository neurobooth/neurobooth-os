# Single-Machine Testing

This document describes the steps required to run Neurobooth on a single machine for testing purposes. There is currently no support for running a production neurobooth on a single machine.

You must be running Windows 10 or greater to run Neurobooth.

## Configuration
To run on a single machine you must modify the neurobooth config file, typically "neurobooth_os_config.json". 
The following changes should be applied:
- The entries for acquisition, control, and presentation must have name, user, and password all set to  "".
- The entries for acquisition, control, and presentation must have port set to different values
- TODO: Describe how to set the monitor width, etc.

If you're running the db on the same machine as the neurobooth code, the following additional changes are required:
- The database host value should be set to the loopback address "127.0.0.1"

## Servers
ACQ and STM servers are started via the GUI using WMI. See the [WMI instructions](enable_WMI_instuctions.txt) to get started. 
WMI invokes the server_acq and server_stm batch file scripts to run the servers. The first the scripts are invoked this way
they are added to the Windows Task Scheduler and then run almost immediately afterward. You can view the tasks in the scheduler for troubleshooting.

Please Note: When the tasks are first added to the scheduler, they are created with a number of default settings, one of which
causes the task to not run if the machine is not running on AC power.  You should probably change that if you plan to work 
on a laptop and may run on battery. 

## Database
You can run the Neurobooth servers on one machine, without also running the database on that machine. 
Sometimes however, it is helpful to also run the database on the same machine. For example, you may want to avoid using the VPN or to perform testing while disconnected from the Net. 

The first step is to install a working copy of PostgreSQL and PGAdmin.  While PGAdmin isn't strictly necessary, the steps described here will assume it is used.

1. Create a database on the local server
2. Make a schema-only backup of a current Neurobooth database, from either production or another test environment.
3. Run a script to add a single user. The file extras/add_test_user.sql contains SQL to add the user.

When running on one machine, we do not use an SSH tunnel to connect to the database. 

## Debugging
In order to run the GUI from within Pycharm, we must add PYDEVD_USE_FRAME_EVAL=NO to the list of environment variables specified in the Pycharm run configuration. 
This is due to a known issue that occurs when running the Pycharm/python debugger on a QT based GUI. 
The issue causes a python interpreter crash with the error message "Process finished with exit code -1073741819 (0xC0000005)"

PyCharm should be run as Administrator so the PyCharm interpreter will have adequate permissions.

# Miscellaneous
If you want to run from your development environment, it will add a server_pids.txt file to the neurobooth_os folder. This can  be ignored. 