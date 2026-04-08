# Config Normalization

## Problem

The current config structure uses a single `ServerSpec` model for both machine-level
and service-level information. This conflation creates three related problems:

### 1. Duplicated machine information

When multiple services run on the same physical machine, every field that describes
the machine (`name`, `user`, `password`, `local_data_dir`) is copied verbatim into
each service entry. In the current production layout, `acquisition[1]` and
`presentation` both run on the STM machine and carry identical values for these
fields. Adding a third acquisition service on that machine would mean the same
machine info appears three times — and the same password appears in `secrets.yaml`
three times.

Example from current staging config:
```json
"acquisition": [
    {
        "name": "acq-staging",
        "user": "TEST_ACQ",
        "local_data_dir": "E:/neurobooth/test/neurobooth_data/",
        "bat": "...", "task_name": "acq-staging",
        "devices": ["Intel_D455_1", "FLIR_blackfly_1", "..."]
    },
    {
        "name": "stm-staging",
        "user": "TEST_STM",
        "local_data_dir": "C:/Users/TEST_STM/nb_os_env/neurobooth_data/",
        "bat": "...", "task_name": "acq-stm-staging",
        "devices": ["Mouse", "Mbient_LF_2", "Mbient_RF_2"]
    }
],
"presentation": {
    "name": "stm-staging",
    "user": "TEST_STM",
    "local_data_dir": "C:/Users/TEST_STM/nb_os_env/neurobooth_data/",
    "bat": "...", "task_name": "stm-staging",
    "devices": ["Eyelink_1"]
}
```

`name`, `user`, and `local_data_dir` for `acquisition[1]` and `presentation` are
identical because they describe the same machine.

### 2. Index-dependent secret merging (#597)

`_deep_merge()` matches `secrets.yaml` entries to config entries by list index.
For the `acquisition` array, the order and count in `secrets.yaml` must exactly
match the config file. Inserting or reordering acquisition entries silently assigns
passwords to the wrong service. This has caused breakage in staging when adding a
new acquisition service before an existing entry.

### 3. Over-distributed credentials (credential_management.md)

`ServerSpec.password` is a required field. Pydantic validates the entire model at
startup, so every machine needs a `secrets.yaml` containing passwords for all
servers — even though only CTR uses the service passwords (for remote process
management via `SCHTASKS`, `taskkill`, `WMIC`). ACQ and STM machines end up with
passwords they never use.

### Root cause

All three problems stem from the same design choice: `ServerSpec` represents both
"what machine is this" and "what service runs on it." Separating these two concepts
solves all three problems simultaneously.

## Proposed Design

### New config structure

Split the current `ServerSpec` into two concepts:

**Machines** — physical or logical hosts, defined once by name in a top-level
`machines` dict. Each entry carries the fields that describe the host itself:

```yaml
machines:
  acq-prod:
    user: NB_ACQ
    local_data_dir: "E:/neurobooth_data/"
    local_log_dir: "E:/neurobooth_logs/"
  stm-prod:
    user: NB_STM
    local_data_dir: "C:/Users/NB_STM/neurobooth_data/"
    local_log_dir: "C:/Users/NB_STM/neurobooth_logs/"
  ctr-prod:
    user: NB_CTR
    local_data_dir: "C:/Users/NB_CTR/neurobooth_data/"
    local_log_dir: "C:/Users/NB_CTR/neurobooth_logs/"
```

**Services** — reference the machine they run on and add only service-specific
fields (`bat`, `task_name`, `devices`):

```yaml
acquisition:
  - machine: acq-prod
    bat: "%NB_INSTALL%/neurobooth_os/server_acq.bat"
    task_name: acq-prod
    devices:
      - Intel_D455_1
      - Intel_D455_2
      - FLIR_blackfly_1
      - Mic_Yeti_1
  - machine: stm-prod
    bat: "%NB_INSTALL%/neurobooth_os/server_acq.bat"
    task_name: acq-stm-prod
    devices:
      - Mouse
      - Mbient_LF_2
      - Mbient_RF_2
presentation:
  machine: stm-prod
  bat: "%NB_INSTALL%/neurobooth_os/server_stm.bat"
  task_name: stm-prod
  devices:
    - Eyelink_1
control:
  machine: ctr-prod
```

Note: the examples use YAML to match the direction of the config format, but the
same structure applies if the config remains JSON.

### New secrets structure

Secrets are keyed by machine name instead of by service list index:

**CTR machine** (has database password and passwords for machines it manages):
```yaml
production:
  database:
    password: "db_password"
  machines:
    acq-prod:
      password: "acq_windows_password"
    stm-prod:
      password: "stm_windows_password"
```

**ACQ and STM machines** (only need database password):
```yaml
production:
  database:
    password: "db_password"
```

No `ctr-prod` password entry anywhere — CTR is never managed remotely.

### New Pydantic models

```python
class MachineSpec(BaseModel):
    """A physical or logical host."""
    user: str
    password: Optional[SecretStr] = None  # Only needed by CTR for remote management
    local_data_dir: str
    local_log_dir: str


class ServiceSpec(BaseModel):
    """A neurobooth service running on a machine."""
    machine: str                          # Key into the machines dict
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
    acquisition: List[ServiceSpec]
    presentation: ServiceSpec
    control: ServiceSpec
    database: DatabaseSpec
    screen: ScreenSpec
```

### Resolved view

Most call sites today work with `ServerSpec` and access a mix of machine-level
fields (`name`, `user`, `password`, `local_data_dir`) and service-level fields
(`bat`, `task_name`, `devices`). Rather than rewriting every call site, provide a
`ResolvedService` that flattens both layers:

```python
class ResolvedService(BaseModel):
    """Flattened view combining machine and service info.

    Returned by server_by_name() so existing call sites do not change.
    """
    # Machine fields
    name: str               # Machine key (was ServerSpec.name)
    user: str
    password: Optional[SecretStr] = None
    local_data_dir: str
    local_log_dir: str
    # Service fields
    bat: Optional[str] = None
    task_name: Optional[str] = None
    devices: List[str] = []
```

`server_by_name()` and `current_server()` return `ResolvedService` instances,
constructed at config load time by joining each service entry with its machine
entry. Call sites that use `s.name`, `s.user`, `s.password`, `s.local_data_dir`,
`s.bat`, `s.task_name`, or `s.devices` continue to work unchanged.

```python
def server_by_name(self, server_name: str) -> ResolvedService:
    # Same dispatch logic as today, but returns ResolvedService
    ...
```

### Secret merging

`_deep_merge()` no longer needs to handle index-based list matching for
credentials. The `machines` section in `secrets.yaml` is a dict keyed by machine
name, which merges naturally with the `machines` section in the config via the
existing dict-merge path. This fully resolves #597 — there is no positional
coupling between secrets and config entries.

The `acquisition` list in the config file contains only service-level fields (no
passwords), so the index-fragility problem disappears. There is nothing
security-sensitive in the service entries to merge.

### current_server_name() changes

The current implementation matches `USERPROFILE` against `ServerSpec.user` to
disambiguate multiple acquisition services on different machines. With
normalization, this becomes a machine-level lookup:

```python
def current_server_name(self) -> str:
    server_name = get_server_name_from_env()
    if server_name is None:
        raise ConfigException('Could not detect current server from local environment.')
    if server_name == 'acquisition' and len(self.acquisition) > 1:
        user_profile = getenv("USERPROFILE", "").upper()
        for i, acq in enumerate(self.acquisition):
            machine = self.machines[acq.machine]
            if machine.user.upper() in user_profile:
                return f'acquisition_{i}'
        raise ConfigException(
            f'Could not match USERPROFILE "{getenv("USERPROFILE")}" '
            f'to any acquisition server.'
        )
    return server_name
```

The logic is the same — the only difference is the user field is read from the
machine entry instead of the service entry.

### Password validation

Service passwords remain optional. The guard moves to `netcomm/client.py` where
passwords are actually consumed:

```python
def start_server(node_name, acq_index=None, save_pid_txt=True):
    ...
    s = cfg.neurobooth_config.server_by_name(node_name)
    if s.password is None:
        raise cfg.ConfigException(
            f"Cannot start remote server '{node_name}': no password configured. "
            f"Service passwords are required in secrets.yaml on the control machine."
        )
    ...
```

This applies to `start_server()` and `kill_remote_pid()`. The error message is
explicit and actionable, replacing the generic Pydantic validation failure that
occurs today when a password is missing.

## How this solves each problem

| Problem | Root cause | How normalization fixes it |
|---------|-----------|--------------------------|
| Duplicated machine info | ServerSpec mixes machine + service fields | Machine fields defined once in `machines` dict, referenced by name |
| Index-dependent merging (#597) | Secrets matched by list position | Secrets keyed by machine name; no list-position coupling |
| Over-distributed credentials | Every ServerSpec requires a password | Password on MachineSpec is optional; only CTR's secrets file includes remote machine passwords |
| Dead control password | control.password required but unused | CTR machine entry exists but needs no password — no one manages CTR remotely |
| Repeated passwords | Same password in every service on a machine | One password per machine, regardless of how many services run there |
| local_log_dir (#662) | Would need to be added to every service entry | Added once per machine in MachineSpec |

## What does not change

- **Config file format.** Still YAML (or JSON), still keyed by environment.
- **`_load_secrets` resolution order.** Still checks `NB_SECRETS` env var first.
- **`DatabaseSpec`.** Unchanged — `database.password` remains required.
- **Message routing.** `ACQ_0`, `ACQ_1` indexing is unchanged at runtime.
  Service IDs are still derived from the acquisition array index.
- **`server_by_name()` return type contract.** Returns an object with `name`,
  `user`, `password`, `local_data_dir`, `bat`, `task_name`, `devices` — all the
  same attributes call sites use today.

## Migration

### Phase 1: Add machine/service models alongside existing

1. Add `MachineSpec`, `ServiceSpec`, and `ResolvedService` to `config.py`.
2. Update `NeuroboothConfig` to accept either the old flat structure or the new
   normalized structure. Detect which format is in use by checking for the
   `machines` key.
3. When the old format is detected, internally convert to the new structure at
   load time (construct synthetic `MachineSpec` entries from the flat
   `ServerSpec` fields). This keeps all downstream code working on the new
   models immediately.
4. `server_by_name()` returns `ResolvedService` in both cases.

### Phase 2: Migrate config files

1. Convert environment configs to the new structure one at a time.
2. Convert `secrets.yaml` files to use machine-keyed passwords.
3. Old-format configs continue to work via the Phase 1 compatibility layer.

### Phase 3: Remove compatibility layer

Once all environments are migrated, remove the old-format detection and the
synthetic conversion logic.

## Implementation scope

### Files to change

| File | Change |
|------|--------|
| `config.py` | Add `MachineSpec`, `ServiceSpec`, `ResolvedService`. Update `NeuroboothConfig` fields and methods. Add old-format compatibility shim. |
| `netcomm/client.py` | Add password guards in `start_server()` and `kill_remote_pid()`. |
| `config.py` (`validate_system_paths`) | Validate `local_log_dir` alongside `local_data_dir`. |
| `config.py` (`_deep_merge`) | No changes needed — dict-keyed machines merge naturally. |
| Example configs | Update to new structure. |
| `docs/arch/system_architecture.md` | Update Configuration Schema section. |
| `docs/arch/system_configuration.md` | Update Secrets section. |

### Files that should not need changes

Call sites that use `server_by_name()`, `current_server()`, or index into
`neurobooth_config.acquisition[i]` should not change, because `ResolvedService`
exposes the same attributes as the current `ServerSpec`. The following files
access `ServerSpec` attributes and should be verified but not modified:

- `session_controller.py`
- `server_acq.py`
- `stm_session.py`
- `layouts.py`
- `transfer_data.py`
- `tasks/eye_tracker_calibrate.py`
- `iout/lsl_streamer.py`
- `extras/dump_iphone_video.py`

## Related issues

- **#597** — Match secrets to config entries by name instead of list index.
  Fully addressed by machine-keyed secrets.
- **#661** — Windows Credential Manager (`keyring`) as secret backend.
  Orthogonal to this change. `keyring` would replace `secrets.yaml` as the
  source for `MachineSpec.password` values. The normalized structure makes this
  easier — `keyring` lookups would be keyed by machine name.
- **#662** — Add `local_log_dir` to server config. Included in `MachineSpec`
  as part of this design.
