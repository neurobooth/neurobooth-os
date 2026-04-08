# -*- coding: utf-8 -*-
"""
Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""

import logging
from os import environ, path, getenv
from typing import Dict, Optional, List

import yaml
from pydantic import BaseModel, PrivateAttr, SecretStr, conlist


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
    password: SecretStr
    host: str
    port: int
    ssh_tunnel: bool
    remote_user: str
    remote_host: str


class ServerSpec(BaseModel):
    """Legacy flat model — kept for old-format config compatibility."""
    name: str
    user: str
    password: SecretStr
    local_data_dir: str
    bat: Optional[str] = None
    task_name: Optional[str] = None
    devices: List[str] = []


class MachineSpec(BaseModel):
    """A physical or logical host."""
    user: str
    password: Optional[SecretStr] = None
    local_data_dir: str
    local_log_dir: Optional[str] = None


class ServiceSpec(BaseModel):
    """A neurobooth service running on a machine."""
    machine: str
    bat: Optional[str] = None
    task_name: Optional[str] = None
    devices: List[str] = []


class ResolvedService(BaseModel):
    """Flattened view combining machine and service info.

    Returned by server_by_name() so existing call sites do not change.
    """
    name: str
    user: str
    password: Optional[SecretStr] = None
    local_data_dir: str
    local_log_dir: Optional[str] = None
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
    machines: Dict[str, MachineSpec]
    database: DatabaseSpec
    screen: ScreenSpec

    _acquisition_specs: List[ServiceSpec] = PrivateAttr(default_factory=list)
    _presentation_spec: Optional[ServiceSpec] = PrivateAttr(default=None)
    _control_spec: Optional[ServiceSpec] = PrivateAttr(default=None)
    _resolved: Dict[str, ResolvedService] = PrivateAttr(default_factory=dict)

    def __init__(self, **data):
        # Detect old-format config (no 'machines' key, acquisition entries have 'user')
        if 'machines' not in data:
            data = _convert_legacy_config(data)
        # Pull service specs out before Pydantic validation (they're private fields)
        acq_specs = [ServiceSpec(**s) for s in data.pop('acquisition', [])]
        pres_spec = ServiceSpec(**data.pop('presentation', {}))
        ctrl_spec = ServiceSpec(**data.pop('control', {}))
        super().__init__(**data)
        self._acquisition_specs = acq_specs
        self._presentation_spec = pres_spec
        self._control_spec = ctrl_spec
        self._resolved = _build_resolved_cache(self)

    @property
    def acquisition(self) -> List[ResolvedService]:
        """Return resolved acquisition services (preserves index-based access)."""
        return [self._resolved[f'acquisition_{i}']
                for i in range(len(self._acquisition_specs))]

    @property
    def presentation(self) -> ResolvedService:
        """Return resolved presentation service."""
        return self._resolved['presentation']

    @property
    def control(self) -> ResolvedService:
        """Return resolved control service."""
        return self._resolved['control']

    def acq_service_id(self, index: int) -> str:
        """Message routing identifier for acquisition server at index."""
        return f"ACQ_{index}"

    def all_acq_service_ids(self) -> List[str]:
        """Return message routing identifiers for all acquisition servers."""
        return [self.acq_service_id(i) for i in range(len(self._acquisition_specs))]

    def get_acq_for_device(self, device_id: str) -> int:
        """Return the index of the acquisition server that owns a given device."""
        for i, acq in enumerate(self._acquisition_specs):
            if device_id in acq.devices:
                return i
        raise ConfigException(f"Device '{device_id}' not found in any acquisition server.")

    def current_server_name(self) -> str:
        """Resolve the fully-qualified server name for the current machine.

        Returns a name usable with :meth:`server_by_name`, e.g.
        ``'presentation'``, ``'control'``, or ``'acquisition_0'``.

        When the generic role ``'acquisition'`` is detected and multiple
        acquisition servers exist, the OS username (from ``USERPROFILE``) is
        matched against each acquisition server's ``user`` field to determine
        the correct index.
        """
        server_name = get_server_name_from_env()
        if server_name is None:
            raise ConfigException('Could not detect current server from local environment.')
        if server_name == 'acquisition' and len(self._acquisition_specs) > 1:
            user_profile = getenv("USERPROFILE", "").upper()
            for i, acq in enumerate(self._acquisition_specs):
                machine = self.machines[acq.machine]
                if machine.user.upper() in user_profile:
                    return f'acquisition_{i}'
            raise ConfigException(
                f'Could not match USERPROFILE "{getenv("USERPROFILE")}" '
                f'to any acquisition server.'
            )
        return server_name

    def current_server(self) -> ResolvedService:
        return self.server_by_name(self.current_server_name())

    def server_by_name(self, server_name: str) -> ResolvedService:
        if server_name.startswith('acquisition_'):
            idx = int(server_name.split('_')[1])
            key = f'acquisition_{idx}'
            if key in self._resolved:
                return self._resolved[key]
            raise ConfigException(f'Acquisition index {idx} out of range.')
        if server_name == 'acquisition':
            if len(self._acquisition_specs) == 1:
                return self._resolved['acquisition_0']
            raise ConfigException('Multiple acquisition servers. Use acquisition_N.')
        if server_name in self._resolved:
            return self._resolved[server_name]
        raise ConfigException(f'Invalid server name: {server_name}')


def _resolve_service(machines: Dict[str, MachineSpec], service: ServiceSpec,
                     name_override: Optional[str] = None) -> ResolvedService:
    """Join a ServiceSpec with its MachineSpec to produce a ResolvedService."""
    machine_name = service.machine
    if machine_name not in machines:
        raise ConfigException(f"Service references unknown machine '{machine_name}'.")
    m = machines[machine_name]
    return ResolvedService(
        name=name_override or machine_name,
        user=m.user,
        password=m.password,
        local_data_dir=m.local_data_dir,
        local_log_dir=m.local_log_dir,
        bat=service.bat,
        task_name=service.task_name,
        devices=service.devices,
    )


def _build_resolved_cache(cfg: NeuroboothConfig) -> Dict[str, ResolvedService]:
    """Pre-resolve all services into a lookup dict."""
    resolved = {}
    for i, acq in enumerate(cfg._acquisition_specs):
        resolved[f'acquisition_{i}'] = _resolve_service(cfg.machines, acq)
    resolved['presentation'] = _resolve_service(cfg.machines, cfg._presentation_spec)
    resolved['control'] = _resolve_service(cfg.machines, cfg._control_spec)
    return resolved


def _convert_legacy_config(data: dict) -> dict:
    """Convert old flat ServerSpec config to normalized machines + services format."""
    machines = {}

    def _extract_machine(entry: dict) -> str:
        """Pull machine fields out of a flat ServerSpec dict, return machine key."""
        name = entry['name']
        if name not in machines:
            machine_data = {'user': entry['user'], 'local_data_dir': entry['local_data_dir']}
            if 'password' in entry:
                machine_data['password'] = entry['password']
            machines[name] = machine_data
        return name

    def _make_service(entry: dict, machine_key: str) -> dict:
        return {
            'machine': machine_key,
            'bat': entry.get('bat'),
            'task_name': entry.get('task_name'),
            'devices': entry.get('devices', []),
        }

    # Convert acquisition list
    new_acq = []
    for acq_entry in data.get('acquisition', []):
        mk = _extract_machine(acq_entry)
        new_acq.append(_make_service(acq_entry, mk))

    # Convert presentation
    pres = data.get('presentation', {})
    pres_mk = _extract_machine(pres)
    new_pres = _make_service(pres, pres_mk)

    # Convert control
    ctrl = data.get('control', {})
    ctrl_mk = _extract_machine(ctrl)
    new_ctrl = _make_service(ctrl, ctrl_mk)

    data = dict(data)
    data['machines'] = machines
    data['acquisition'] = new_acq
    data['presentation'] = new_pres
    data['control'] = new_ctrl
    return data


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
        env_name: Value of the ``environment`` field from the config file,
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

    server = neurobooth_config.server_by_name(server_name)
    source = server.local_data_dir
    if not path.exists(source):
        raise FileNotFoundError(f"The local_data_dir '{source}' for server {server_name} does not exist.")
    if not path.isdir(source):
        raise ConfigException(f"The local_data_dir '{source}' for server {server_name} is not a folder.")

    if server.local_log_dir is not None:
        log_dir = server.local_log_dir
        if not path.exists(log_dir):
            raise FileNotFoundError(f"The local_log_dir '{log_dir}' for server {server_name} does not exist.")
        if not path.isdir(log_dir):
            raise ConfigException(f"The local_log_dir '{log_dir}' for server {server_name} is not a folder.")


def load_neurobooth_config(fname: Optional[str] = None):
    if fname is None:
        config_dir = environ.get("NB_CONFIG")
        if config_dir is None:
            raise ConfigException(
                "NB_CONFIG environment variable is not set and no file path was provided."
            )
        fname = path.join(config_dir, "neurobooth_os_config.yaml")
    else:
        config_dir = path.dirname(path.abspath(fname))

    if not path.exists(fname):
        raise ConfigException(f'Required config file does not exist: {fname}')

    with open(fname, "r") as f:
        config_data = yaml.safe_load(f)

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
        validate_system_paths(neurobooth_config.current_server_name())
