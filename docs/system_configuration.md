# System Configuration

As described in release_process.md, deployments should generally be made from packaged releases managed in GitHub, using git's checkout function. 
This document assumes that step has been completed.

Once the new code is checked-out, configuration data may need to be updated, and config files may need to be created or modified. Neurobooth provides example files that can be used in this process. They can be found in the neurobooth-os/examples/configs.

Please note that the process described here is completely manual, so that no config data is accidentally over-written during deployment.
Consult the release notes for any modifications to the example files, as these modifications serve sa notice that changes were made to configuration data, and that some additional data may be required. 

## Config files
At least one config file (neurobooth_os_config.json) should be modified as necessary and placed in the folder named in the NB_CONFIG environment variable. (See below)
Any additional config files required by the system will also be placed in this folder or in a sub-folder. It is expected that device-specific config files will be placed in a sub-folder called "devices".

## Environment Variables
Several environment variables must be setup to run neurobooth. An example Windows batch file can be found that creates all the required variables (or updates them if they already exist). 
There are two files provided, one for a staging environment, and the other for a production environment. 
It is good practice to maintain separate files for each environment that you will deploy to regularly.

As you can see from the examples, the environment variables include locations, including the install folder for neurobooth, and the config folder. The config folder variable ("NB_CONFIG") states the location of the other config files. 
Neurobooth cannot run if the required configuration file(s) are not found there.

