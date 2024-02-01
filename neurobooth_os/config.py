# -*- coding: utf-8 -*-
"""
Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""

from os import environ, path, getenv
from typing import Optional
from typing_extensions import Annotated
from pydantic import BaseModel, Field
import json


def get_server_name_from_env() -> Optional[str]:
    """
    This is a hack to get the role of the machine that this code is being executed on. It's based on the
    assumption that the Windows User Profile in use matches one of the servers defined in the config file
    :returns: a server name, or None.
    """
    user = getenv("USERPROFILE")

    if "STM" in user:
        return 'presentation'
    if "ACQ" in user:
        return 'acquisition'
    if "CTR" in user:
        return 'control'

    return None


def validate_folder(value: str) -> None:
    if not path.exists(value):
        raise FileNotFoundError(f"The folder '{value}' does not exist.")
    if not path.isdir(value):
        raise IOError(f"The path '{value}' is not a folder.")


class DatabaseSpec(BaseModel):
    dbname: str
    user: str
    password: Annotated[str, Field(alias='pass')]
    host: str
    port: int
    remote_user: Annotated[str, Field(alias='remote_username')]
    remote_host: Annotated[str, Field(alias='remote_address')]


class ServerSpec(BaseModel):
    name: str
    user: str
    password: Annotated[str, Field(alias='pass')]
    port: int
    local_data_dir: str
    bat: Optional[str] = None


class NeuroboothConfig(BaseModel):
    default_log_path: str
    remote_data_dir: str
    video_task_dir: Annotated[str, Field(alias='video_tasks')]
    cam_inx_lowfeed: int
    acquisition: ServerSpec
    presentation: ServerSpec
    control: ServerSpec
    database: DatabaseSpec


neurobooth_config = None
neurobooth_config_pydantic: Optional[NeuroboothConfig] = None


def load_config(fname: Optional[str] = None, validate_paths: bool = True) -> None:
    """
    Load neurobooth configurations from a file and store them in the `neurobooth_config` module variable.

    :param fname: Path to the configuration file. If None, load the path from the NB_CONFIG environment variable.
    :param validate_paths: Whether to check the validity of key files and directories. Should be True for active
        Nuerobooth sessions. (Toggle is provided for use by secondary scripts.)
    """
    if fname is None:
        fname = path.join(environ.get("NB_CONFIG"), "neurobooth_os_config.json")

    if not path.exists(fname):
        msg = "Required config file does not exist"
        raise IOError(msg)

    with open(fname, "r") as f:
        global neurobooth_config
        neurobooth_config = json.load(f)

        if validate_paths:
            server_name = get_server_name_from_env()
            if server_name is None:
                raise IOError('The server name could not be identified!')

            if server_name == "presentation":
                validate_folder(neurobooth_config["video_tasks"])
            validate_folder(neurobooth_config["remote_data_dir"])
            validate_folder(neurobooth_config["default_log_path"])

            source = neurobooth_config[server_name]["local_data_dir"]
            if not path.exists(source):
                raise FileNotFoundError(f"The local_data_dir '{source}' for server {server_name} does not exist.")
            if not path.isdir(source):
                raise IOError(f"The local_data_dir '{source}' for server {server_name} is not a folder.")

        # TODO: This is a stopgap. Update everything to use the structured model and validate with pydantic.
        global neurobooth_config_pydantic
        neurobooth_config_pydantic = NeuroboothConfig(**neurobooth_config)

