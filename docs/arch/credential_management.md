# Credential Management

## Overview

Credentials are stored in `secrets.yaml`, located in the config folder alongside
`neurobooth_os_config.yaml` (`NB_CONFIG`). At startup,
`config.load_neurobooth_config()` deep-merges `secrets.yaml` into the base config
and constructs a single `NeuroboothConfig` model.

Each machine only needs the credentials it actually uses — the database password,
plus (on the CTR machine only) the Windows passwords needed to remotely manage
the ACQ/STM machines.

## Schema

Credentials live on two Pydantic models in `neurobooth_os/config.py`:

```python
class DatabaseSpec(BaseModel):
    ...
    password: SecretStr   # required — every process needs DB access

class MachineSpec(BaseModel):
    """A physical or logical host."""
    user: str
    password: Optional[SecretStr] = None   # optional — only CTR uses these
    local_data_dir: str
    local_log_dir: Optional[str] = None
```

`ResolvedService` (returned by `NeuroboothConfig.server_by_name()`) inherits the
`password` field from its `MachineSpec` via `_resolve_service`. The same physical
machine can host multiple services, and the password is per-machine, not
per-service.

## secrets.yaml

Keyed by environment name (e.g. `production`, `staging`); the active environment
is selected by the `environment` field in `neurobooth_os_config.yaml`. Within
each environment, secrets are deep-merged into the corresponding sections of the
base config — so `machines.<name>.password` in `secrets.yaml` populates the
`password` field of the matching `MachineSpec`.

### CTR machine

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

### ACQ and STM machines

```yaml
production:
  database:
    password: "db_password"
```

Each machine gets only the secrets it actually uses. The control machine itself
does not need (or have) a Windows password in `secrets.yaml` — nothing manages
CTR remotely.

## Validation

`MachineSpec.password` being optional means config loading succeeds regardless of
which Windows passwords are present. Validation happens at the point of use
rather than at load time:

```python
# neurobooth_os/netcomm/client.py
s = cfg.neurobooth_config.server_by_name(node_name)
if s.password is None:
    raise cfg.ConfigException(
        f"Cannot start remote server '{node_name}': no password configured. "
        f"Service passwords are required in secrets.yaml on the control machine."
    )
```

The same guard exists in `kill_remote_pid()`. Any consumer that tries to use a
missing password gets a clear, actionable error rather than a startup-time
Pydantic failure on every machine that doesn't need that credential.

## Credential inventory

| Credential | Purpose | CTR | ACQ | STM |
|------------|---------|-----|-----|-----|
| `database.password` | PostgreSQL auth | Required | Required | Required |
| `machines.<acq-host>.password` | Remote process management of ACQ | Required | - | - |
| `machines.<stm-host>.password` | Remote process management of STM | Required | - | - |
| SSH key (`~/.ssh/id_rsa`) | SSH tunnel to DB | Required | Required | Required |

The SSH tunnel key path is currently hardcoded to `~/.ssh/id_rsa` in
`metadator.get_database_connection()`. Whether a tunnel is actually opened
depends on `database.ssh_tunnel` and whether `database.host` is `127.0.0.1` /
`localhost` — see `metadator.py` for the gating.
