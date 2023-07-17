"""
    Moves data from local storage to network storage
"""
import subprocess
import sys

from neurobooth_os import config

server_names = ("presentation", "acquisition", "control")

if len(sys.argv) < 2:
    raise Exception("Server name is a required argument for this script.")

server_name = sys.argv[1]

if server_name is None or server_name == '':
    raise Exception("You must provide a server name to transfer data")

if server_name not in server_names:
    raise Exception(f"The server name argument must be one of {server_names}.")

destination = config.neurobooth_config["remote_data_dir"]

source = config.neurobooth_config[server_name]["data_out"]

# Move data to remote
result_step_1 = subprocess.run(["robocopy", "/MOVE", source, destination, "/e"])
print(str(result_step_1))

# Recreate local data folder
result_step_2 = subprocess.run(["mkdir", source])
print(str(result_step_2))
