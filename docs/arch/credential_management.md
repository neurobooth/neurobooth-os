# Credential Management Design

## Current State

### How credentials work today

All credentials live in `secrets.yaml`, keyed by environment name. At startup,
`config.load_neurobooth_config()` deep-merges `secrets.yaml` into the base config
and constructs a single `NeuroboothConfig` Pydantic model that includes every server
definition, regardless of which process is loading it.

```yaml
# secrets.yaml (current structure)
production:
  database:
    password: "db_password_here"
  acquisition:
    - password: "acq0_windows_password"
    - password: "acq1_windows_password"
  presentation:
    password: "stm_windows_password"
  control:
    password: "ctr_windows_password"
```

### Problems

1. **Every machine needs every password.** `ServerSpec.password` is a required field
   with no default. Pydantic validates the entire model at startup, so even an ACQ
   server that never uses the control password will fail to start if it is missing.

2. **Over-distribution of credentials.** To satisfy validation, every machine gets a
   copy of `secrets.yaml` containing passwords for all servers. ACQ and STM machines
   end up with Windows remote-management passwords they never use.

3. **Only CTR uses service passwords.** The `ServerSpec.password` fields are consumed
   exclusively by `netcomm/client.py` for remote process management (`tasklist`,
   `taskkill`, `SCHTASKS`, `WMIC`). Only the CTR process calls these functions.

4. **CTR does not need its own service password.** The `control.password` field is
   never read at runtime. CTR uses the acquisition and presentation passwords to
   manage remote servers, but nobody manages CTR remotely.

5. **The control password field is dead weight.** It must be present to pass validation
   but serves no purpose.

## Requirements

- ACQ and STM machines should only need the database password.
- CTR should have the database password plus the service passwords for the machines
  it manages.
- No machine should receive credentials it does not use.
- The solution should not require maintaining multiple config files per environment.
- Operational burden should be minimal — the current single `secrets.yaml` per
  machine approach is desirable for its simplicity.

## Proposed Design

### Make service passwords optional

Change `ServerSpec.password` from required to optional with a `None` default:

```python
class ServerSpec(BaseModel):
    name: str
    user: str
    password: Optional[SecretStr] = None  # Only needed by CTR for remote management
    local_data_dir: str
    bat: Optional[str] = None
    task_name: Optional[str] = None
    devices: List[str] = []
```

This is the minimal change. Config loading succeeds regardless of which passwords are
present. No structural changes to `secrets.yaml` or `NeuroboothConfig`.

### Validate at point of use, not at load time

Add a check in `netcomm/client.py` where the password is actually consumed:

```python
def start_server(s: ServerSpec, ...):
    if s.password is None:
        raise ConfigException(
            f"Cannot start remote server '{s.name}': no password configured. "
            f"Service passwords are required in secrets.yaml on the control machine."
        )
    password = s.password.get_secret_value()
    ...
```

This gives a clear error message if CTR is missing a needed password, rather than a
generic Pydantic validation error at startup.

### Per-machine secrets files

With the above change, each machine gets a minimal `secrets.yaml`:

**ACQ and STM machines:**
```yaml
production:
  database:
    password: "db_password_here"
```

**CTR machine:**
```yaml
production:
  database:
    password: "db_password_here"
  acquisition:
    - password: "acq0_windows_password"
    - password: "acq1_windows_password"
  presentation:
    password: "stm_windows_password"
```

No `control.password` entry anywhere — it is never used.

## Implementation

The change touches three files:

1. **`config.py`** — Change `ServerSpec.password` to `Optional[SecretStr] = None`.

2. **`netcomm/client.py`** — Add a guard at the top of `start_server()` and
   `kill_remote_pid()` that raises `ConfigException` if `s.password is None`.
   This replaces the implicit Pydantic validation with an explicit, actionable error.

3. **`docs/arch/system_configuration.md`** — Document which secrets each machine
   needs.

### What does not change

- `secrets.yaml` format (still YAML, still keyed by environment).
- `_deep_merge` logic (still merges by index for lists).
- `_load_secrets` resolution order (still checks `NB_SECRETS` env var first).
- `DatabaseSpec.password` remains required — every process needs it.
- Existing deployments with full `secrets.yaml` on every machine continue to work
  unchanged.

## Migration

This is backward-compatible. Existing `secrets.yaml` files with all passwords
continue to work. Machines can be migrated to minimal secrets files one at a time.
No coordinated rollout is needed.

## Credential inventory

After migration, the credential requirements per machine are:

| Credential | Purpose | CTR | ACQ | STM |
|------------|---------|-----|-----|-----|
| `database.password` | PostgreSQL auth | Required | Required | Required |
| `acquisition[N].password` | Remote process mgmt | Required | - | - |
| `presentation.password` | Remote process mgmt | Required | - | - |
| `control.password` | (unused) | - | - | - |
| SSH key (`~/.ssh/id_rsa`) | SSH tunnel to DB | Required | Required | Required |
