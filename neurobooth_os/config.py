# -*- coding: utf-8 -*-
"""
Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""

import json
import logging
from os import environ, path, getenv
from typing import Optional, List

import yaml
from pydantic import BaseModel, conlist


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
    environment: str
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

logger = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict.

    Lists are merged element-wise so that, e.g., acquisition server entries
    line up by index.  Scalar values in *override* replace those in *base*.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif (
            key in result
            and isinstance(result[key], list)
            and isinstance(value, list)
        ):
            merged = []
            for i in range(max(len(result[key]), len(value))):
                base_item = result[key][i] if i < len(result[key]) else None
                over_item = value[i] if i < len(value) else None
                if (
                    isinstance(base_item, dict)
                    and isinstance(over_item, dict)
                ):
                    merged.append(_deep_merge(base_item, over_item))
                elif over_item is not None:
                    merged.append(over_item)
                else:
                    merged.append(base_item)
            result[key] = merged
        else:
            result[key] = value
    return result


def _load_secrets(config_dir: str, env_name: str) -> Optional[dict]:
    """Load environment-specific secrets from ``secrets.yaml``.

    Resolution order for the secrets file path:
      1. The ``NB_SECRETS`` environment variable, if set.
      2. ``secrets.yaml`` in the same directory as the config file.

    Args:
        config_dir: Directory containing the loaded config file.
        env_name: Value of the ``environment`` field from the config JSON,
            used to select the correct section in ``secrets.yaml``.

    Returns:
        A dict of secret overrides for this environment, or ``None`` if the
        secrets file does not exist or contains no section for the environment.
    """
    secrets_path = getenv("NB_SECRETS")
    if secrets_path is None:
        secrets_path = path.join(config_dir, "secrets.yaml")

    if not path.exists(secrets_path):
        logger.debug("No secrets file found at %s; skipping.", secrets_path)
        return None

    with open(secrets_path, "r") as f:
        all_secrets = yaml.safe_load(f)

    if not isinstance(all_secrets, dict) or env_name not in all_secrets:
        logger.warning(
            "secrets.yaml found but contains no section for environment '%s'.",
            env_name,
        )
        return None

    logger.info(
        "Loaded secrets for environment '%s' from %s", env_name, secrets_path
    )
    return all_secrets[env_name]


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
        config_dir = environ.get("NB_CONFIG")
        if config_dir is None:
            raise ConfigException(
                "NB_CONFIG environment variable is not set and no file path was provided."
            )
        fname = path.join(config_dir, "neurobooth_os_config.json")
    else:
        config_dir = path.dirname(path.abspath(fname))

    if not path.exists(fname):
        raise ConfigException(f'Required config file does not exist: {fname}')

    with open(fname, "r") as f:
        config_data = json.load(f)

    env_name = config_data.get("environment")
    if env_name is not None:
        secrets = _load_secrets(config_dir, env_name)
        if secrets is not None:
            config_data = _deep_merge(config_data, secrets)

    global neurobooth_config
    neurobooth_config = NeuroboothConfig(**config_data)


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
