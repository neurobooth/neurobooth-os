# Single-Machine Testing

This document describes the steps required to run Neurobooth on a single machine for testing purposes. There is currently no support for running a production neurobooth on a single machine.

Note: You must be running Windows 10 or greater to run Neurobooth on your machine.

## Configuration
The main config file is `neurobooth_os_config.yaml`, located in the folder named by the `NB_CONFIG` environment variable. The format is the normalized machines + services layout: a top-level `machines:` dict keyed by machine name, plus `acquisition` / `presentation` / `control` sections that reference machines by name. See [system_configuration.md](arch/system_configuration.md) for the authoritative schema.

For single-machine testing, define one machine in `machines:` with `user` set to `""`, and have all three service sections reference that machine by its dict key. An empty `user` triggers a local-execution shortcut in `netcomm/client.py` so SCHTASKS, Get-CimInstance, and tasklist run on this machine without remote credentials — no Windows password is required, and `machines.<name>.password` should be omitted entirely.

Minimal example (`neurobooth_os_config.yaml`):

```yaml
environment: local
remote_data_dir: C:/data/
video_task_dir: C:/path/to/videos
split_xdf_backlog: C:/neurobooth/split_xdf_backlog.csv
cam_inx_lowfeed: 0
default_preview_stream: IPhoneFrameIndex

screen:
  fullscreen: false
  width_cm: 55
  subject_distance_to_screen_cm: 60
  min_refresh_rate_hz: 50
  max_refresh_rate_hz: 250
  screen_resolution: [1920, 1080]

machines:
  laptop:
    user: ""
    local_data_dir: C:/neurobooth/neurobooth_data/

acquisition:
  - machine: laptop
    bat: "%NB_INSTALL%/neurobooth_os/server_acq.bat"
    task_name: acquisition
    devices:
      - Mic_Yeti_dev_1

presentation:
  machine: laptop
  bat: "%NB_INSTALL%/neurobooth_os/server_stm.bat"
  task_name: presentation
  devices:
    - Mouse
    - marker

control:
  machine: laptop
  devices: []

database:
  ssh_tunnel: false
  dbname: mock_neurobooth
  user: postgres
  host: 127.0.0.1
  port: 5432
  remote_user: <your-windows-username>
  remote_host: 127.0.0.1
```

The top-level `environment:` value (here, `local`) selects which section is loaded from `secrets.yaml`. Passwords live in `secrets.yaml` (in the same folder as `neurobooth_os_config.yaml`, or pointed to by the `NB_SECRETS` env var) and are merged into the config at load time. For local testing the only password you need is the database password:

```yaml
local:
  database:
    password: "<your_db_password>"
```

`machines.<name>.password` is **not** required for single-machine testing; it is only needed on the CTR machine in a multi-machine production deployment.

If you're running the database on the same machine as the neurobooth code, set `database.host` to `127.0.0.1` and `database.ssh_tunnel: false` (as in the example above), and update the other `database` fields (`user`, `dbname`, etc.) to match your local Postgres install.

For more information on configuration settings, see [system_configuration.md](arch/system_configuration.md).

## Servers
ACQ and STM servers are started by the GUI through Windows `SCHTASKS`. On first launch, the GUI registers a scheduled task that runs the appropriate batch file (`server_acq.bat` or `server_stm.bat`) and then triggers it; on subsequent launches the existing task is reused. PowerShell `Get-CimInstance` (over a DCOM `CimSession`) and `tasklist` are used alongside SCHTASKS to inventory and clean up Python processes between runs. You can view and troubleshoot the tasks in the Windows Task Scheduler.

For single-machine testing, you do **not** need to enable remote WMI or configure a domain user — when `machines.<name>.user` is empty, `netcomm/client.py` skips the remote credentials and runs SCHTASKS / Get-CimInstance / tasklist locally on the calling machine. The [inter-machine setup runbook](inter_machine_setup.md) is only relevant for multi-machine production deployments where CTR launches ACQ and STM on separate hosts.

Please Note: When the tasks are first added to the scheduler, they are created with a number of default settings, one of which causes the task to not run if the machine is not running on AC power. You should probably change that if you plan to work on a laptop and may run on battery.

## Database
You can run the Neurobooth servers on one machine without also running the database on that machine. 
Sometimes however, it is helpful to also run the database on the same machine. For example, you may want to avoid using your VPN or to perform testing while disconnected from the Net. 

The first step is to install a working copy of PostgreSQL and PGAdmin.  While PGAdmin isn't strictly necessary, the steps described here will assume it is used.

1. Create a database on the local server
2. Make a schema-only backup of a current Neurobooth database, from either production or another test environment.
3. Run a SQL script to add a single user. The file extras/add_test_user.sql contains SQL to add the user.

When running on one machine, we do not use an SSH tunnel to connect to the database. 

## Studies and Task Collections
Since your local device is unlikely to have the standard devices, a new task collection called "test_no_eyelink" has been added to the "test_study" study config in the examples folder. 
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

