# -*- coding: utf-8 -*-
"""
Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""

from os import environ, path, getenv
from typing import Optional, List
from pydantic import BaseModel, conlist
import json


class ConfigException(Exception):
    pass


def get_server_name(abbreviation: str) -> Optional[str]:
    abbr = abbreviation.upper()
    if "STM" in abbr or "PARTICIPANT" in abbr:
        return 'presentation'
    if "ACQ" in abbr:
        return 'acquisition'
    if "CTR" in abbr or "COORDINATOR" in abbr:
        return 'control'
    return None


def get_server_name_from_env() -> Optional[str]:
    """
    This is a hack to get the role of the machine that this code is being executed on. It's based on the
    assumption that the Windows User Profile in use matches one of the servers defined in the config file
    :returns: a server name, or None.
    """
    user = getenv("USERPROFILE")
    return get_server_name(user)


def validate_folder(value: str) -> None:
    if not path.exists(value):
        raise FileNotFoundError(f"The folder '{value}' does not exist.")
    if not path.isdir(value):
        raise IOError(f"The path '{value}' is not a folder.")


class ScreenSpec(BaseModel):
    fullscreen: bool
    width_cm: int
    subject_distance_to_screen_cm: int
    min_refresh_rate_hz: float
    max_refresh_rate_hz: float
    screen_resolution: conlist(int, min_length=2, max_length=2)


class DatabaseSpec(BaseModel):
    dbname: str
    user: str
    password: str
    host: str
    port: int
    ssh_tunnel: bool
    remote_user: str
    remote_host: str


class ServerSpec(BaseModel):
    name: str
    user: str
    password: str
    local_data_dir: str
    bat: Optional[str] = None
    task_name: Optional[str] = None
    devices: List[str] = []


class NeuroboothConfig(BaseModel):
    remote_data_dir: str
    video_task_dir: str
    split_xdf_backlog: str
    cam_inx_lowfeed: int
    default_preview_stream: str
    acquisition: List[ServerSpec]
    presentation: ServerSpec
    control: ServerSpec
    database: DatabaseSpec
    screen: ScreenSpec

    def acq_service_id(self, index: int) -> str:
        """Message routing identifier for acquisition server at index."""
        return f"ACQ_{index}"

    def all_acq_service_ids(self) -> List[str]:
        """Return message routing identifiers for all acquisition servers."""
        return [self.acq_service_id(i) for i in range(len(self.acquisition))]

    def get_acq_for_device(self, device_id: str) -> int:
        """Return the index of the acquisition server that owns a given device."""
        for i, acq in enumerate(self.acquisition):
            if device_id in acq.devices:
                return i
        raise ConfigException(f"Device '{device_id}' not found in any acquisition server.")

    def current_server(self) -> ServerSpec:
        server_name = get_server_name_from_env()
        if server_name is None:
            raise ConfigException('Could not detect current sever from local environment.')
        return self.server_by_name(server_name)

    def server_by_name(self, server_name: str) -> ServerSpec:
        if server_name.startswith('acquisition_'):
            idx = int(server_name.split('_')[1])
            return self.acquisition[idx]
        if server_name == 'acquisition':
            if len(self.acquisition) == 1:
                return self.acquisition[0]
            raise ConfigException('Multiple acquisition servers. Use acquisition_N.')
        if hasattr(self, server_name):
            server = getattr(self, server_name)
            if isinstance(server, ServerSpec):
                return server
        raise ConfigException(f'Invalid server name: {server_name}')


neurobooth_config: Optional[NeuroboothConfig] = None


def validate_system_paths(server_name: str):
    if server_name == "presentation":
        validate_folder(neurobooth_config.video_task_dir)
    validate_folder(neurobooth_config.remote_data_dir)

    source = neurobooth_config.server_by_name(server_name).local_data_dir
    if not path.exists(source):
        raise FileNotFoundError(f"The local_data_dir '{source}' for server {server_name} does not exist.")
    if not path.isdir(source):
        raise ConfigException(f"The local_data_dir '{source}' for server {server_name} is not a folder.")


def load_neurobooth_config(fname: Optional[str] = None):
    if fname is None:
        fname = path.join(environ.get("NB_CONFIG"), "neurobooth_os_config.json")

    if not path.exists(fname):
        raise ConfigException(f'Required config file does not exist: {fname}')

    with open(fname, "r") as f:
        global neurobooth_config
        neurobooth_config = NeuroboothConfig(**json.load(f))


def load_config_by_service_name(service_abbr: str, acq_index: int = 0, fname: Optional[str] = None,
                                validate_paths: bool = True) -> None:
    """
    Parameters
    ----------
    :param service_abbr: Short name for service, e.g. STM for presentation, CTR for control, ACQ for acquisition.
    :param acq_index: Index of the acquisition server (only used when service_abbr is ACQ).
    :param fname: Path to the configuration file. If None, load the path from the NB_CONFIG environment variable.
    :param validate_paths: Whether to check the validity of key files and directories. Should be True for active
        Neurobooth sessions. (Toggle is provided for use by secondary scripts.)
    """
    load_neurobooth_config(fname)
    server_name = get_server_name(service_abbr)
    if server_name == 'acquisition':
        server_name = f'acquisition_{acq_index}'
    if validate_paths:
        validate_system_paths(server_name)


def load_config(fname: Optional[str] = None, validate_paths: bool = True) -> None:
    """
    Load neurobooth configurations from a file and store them in the `neurobooth_config` module variable.

    :param fname: Path to the configuration file. If None, load the path from the NB_CONFIG environment variable.
    :param validate_paths: Whether to check the validity of key files and directories. Should be True for active
        Nuerobooth sessions. (Toggle is provided for use by secondary scripts.)
    """
    load_neurobooth_config(fname)

    if validate_paths:
        server_name = get_server_name_from_env()
        if server_name is None:
            raise ConfigException('The server name could not be identified!')
        validate_system_paths(server_name)
