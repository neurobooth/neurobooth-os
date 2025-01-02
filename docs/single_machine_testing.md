# Single-Machine Testing

This document describes the steps required to run Neurobooth on a single machine for testing purposes. There is currently no support for running a production neurobooth on a single machine.

Note: You must be running Windows 10 or greater to run Neurobooth on your machine.

## Configuration
To run on a single machine you must modify the neurobooth config file, typically "neurobooth_os_config.json". 
The following changes should be applied:
- The entries for acquisition, control, and presentation must have name, user, and password all set to  "".
- The entries for acquisition, control, and presentation must use different ports since they will all be on the same host.
- TODO: Describe how to set the monitor width, etc.

If you're running the db on the same machine as the neurobooth code, the following additional changes are required:
- The database host value should be set to the loopback address "127.0.0.1"
- You will likely also need to update some of your other database params (e.g. user and password)

For more information on configuration settings, please see: [system_configuration.md](system_configuration.md) 

## Servers
ACQ and STM servers are started via the GUI using WMI. See the [WMI instructions](enable_WMI_instuctions.txt) document to get started. 
WMI invokes the server_acq and server_stm batch file scripts to run the servers. The first the scripts are invoked this way
they are added to the Windows Task Scheduler and then run almost immediately afterward. You can view the tasks in the scheduler for troubleshooting.

Please Note: When the tasks are first added to the scheduler, they are created with a number of default settings, one of which
causes the task to not run if the machine is not running on AC power.  You should probably change that if you plan to work 
on a laptop and may run on battery. 

## Database
You can run the Neurobooth servers on one machine without also running the database on that machine. 
Sometimes however, it is helpful to also run the database on the same machine. For example, you may want to avoid using your VPN or to perform testing while disconnected from the Net. 

The first step is to install a working copy of PostgreSQL and PGAdmin.  While PGAdmin isn't strictly necessary, the steps described here will assume it is used.

1. Create a database on the local server
2. Make a schema-only backup of a current Neurobooth database, from either production or another test environment.
3. Run a SQL script to add a single user. The file extras/add_test_user.sql contains SQL to add the user.

When running on one machine, we do not use an SSH tunnel to connect to the database. 

## Studies and Task Collections
Since your local device is unlikely to have the standard devices, a new task collection called "test_no_eyelink" 
has been added to the "test_study" study config in the examples folder. 
Several new tasks were added to this collection. These tasks: 
- altern_hand_test_obs_1
- foot_tapping_test_obs_1
- sit_to_stand_test_obs
are variations on real tasks, but have fewer device requirements. 
This collection is currently the only one that will work without real devices being attached to the machine used for the test environment.

## Testing your code in PyCharm
The easiest way to run the system on a single machine is to create a Run Configuration in PyCharm that executes gui.py. WIth this 
approach, any changes made to the code can be tested with a mouse click. 

Note: PyCharm should be started as Administrator. This will ensure that the PyCharm interpreter will have adequate permissions.

When running from your development environment, Neurobooth will add a server_pids.txt file to the neurobooth_os folder. This can  be ignored and will be ignored by git. 

### Debugging in PyCharm
In order to run the GUI from within PyCharm, we must add PYDEVD_USE_FRAME_EVAL=NO to the list of environment variables specified in the PyCharm run configuration. 
This is due to a known issue that occurs when running the PyCharm/python debugger on a QT based GUI.
The issue causes a python interpreter crash with the error message "Process finished with exit code -1073741819 (0xC0000005)"

Given that Neurobooth itself starts ACQ and STM, only the gui process can be run directly in PyCharm's interactive debugger. 
To attach the debugger to those processes, follow the instructions at https://www.jetbrains.com/help/pycharm/attach-to-process.html. 
Pycharm can only attach debuggers to local processes so you would need to install it on each server to perform debugging in staging, 
but all three processes can have debuggers attached from your dev environment when running locally. 
 
