# -*- coding: utf-8 -*-
"""
Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""

from os import environ, path, getenv
from typing import Optional
from typing_extensions import Annotated
from pydantic import BaseModel, Field
import json


class ConfigException(Exception):
    pass


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
    password: str
    host: str
    port: int
    remote_user: str
    remote_host: str


class ServerSpec(BaseModel):
    name: str
    user: str
    password: str
    port: int
    local_data_dir: str
    bat: Optional[str] = None


class NeuroboothConfig(BaseModel):
    default_log_path: str
    remote_data_dir: str
    video_task_dir: str
    cam_inx_lowfeed: int
    acquisition: ServerSpec
    presentation: ServerSpec
    control: ServerSpec
    database: DatabaseSpec

    def current_server(self) -> ServerSpec:
        server_name = get_server_name_from_env()
        if server_name is None:
            raise ConfigException('Could not detect current sever from local environment.')
        return self.server_by_name(server_name)

    def server_by_name(self, server_name: str) -> ServerSpec:
        if hasattr(self, server_name):
            server = getattr(self, server_name)
            if isinstance(server, ServerSpec):
                return server
        raise ConfigException(f'Invalid server name: {server_name}')


neurobooth_config: Optional[NeuroboothConfig] = None


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
        raise ConfigException(f'Required config file does not exist: {fname}')

    with open(fname, "r") as f:
        global neurobooth_config
        neurobooth_config = NeuroboothConfig(**json.load(f))

    if validate_paths:
        server_name = get_server_name_from_env()
        if server_name is None:
            raise ConfigException('The server name could not be identified!')

        if server_name == "presentation":
            validate_folder(neurobooth_config.video_task_dir)
        validate_folder(neurobooth_config.remote_data_dir)
        validate_folder(neurobooth_config.default_log_path)

        source = neurobooth_config.current_server().local_data_dir
        if not path.exists(source):
            raise FileNotFoundError(f"The local_data_dir '{source}' for server {server_name} does not exist.")
        if not path.isdir(source):
            raise ConfigException(f"The local_data_dir '{source}' for server {server_name} is not a folder.")
