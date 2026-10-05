# Deploying to a booth environment

`nb_deploy` updates all three machines of an environment (CTR, STM, ACQ) from
one command on that environment's **CTR** machine, and can undo the last
deploy in seconds.

```
%NB_INSTALL%\nb_deploy                          staging: tip of master (neurobooth-os) and main (configs)
%NB_INSTALL%\nb_deploy --os-ref 123-my-branch   any branch, tag or full commit SHA; same for --config-ref
%NB_INSTALL%\nb_deploy --dry-run                show what would change, change nothing
%NB_INSTALL%\nb_deploy rollback                 undo the last deploy (run again to re-apply it)
%NB_INSTALL%\nb_deploy status                   what each machine is running, and what rollback would go back to
```

**Production environments (anything other than `staging`) require both refs:**

```
%NB_INSTALL%\nb_deploy --os-ref v1.2.3 --config-ref v1.2.3
```

The environment is the `environment` field of CTR's active config; override
with `--env <folder under configs/environments>`.

## What a deploy does

1. **Resolve** both refs to commits once, on CTR, so every machine gets the
   same commit even if a branch moves mid-deploy.
2. **Check** every machine. The deploy stops, with nothing changed, if any
   machine is unreachable, has anything running from the install (servers,
   the GUI, scripts — a session may be in progress), has uncommitted edits in
   its `configs` checkout, or has `NB_INSTALL`/`NB_CONFIG` pointing somewhere
   unexpected. Machines already on the requested commits are skipped; if all
   are, it says so and exits.
3. **Build** the new version into each machine's *standby* slot, in parallel:
   git checkout, version stamps, config copy (`shared/` + `environments/<env>/`,
   including the untracked `secrets.yaml`), `uv sync --locked` with that
   machine's extras, then the per-machine step — EyeLink extra where an Eyelink
   device is configured, the Spinnaker wheel where a FLIR device is, the
   LabRecorder swap on CTR. The live install is not touched. If any machine
   fails here, **no machine is switched**.
4. **Switch** each machine to the new slot (STM/ACQ first, then CTR). This is
   two link swaps per machine and takes seconds.

Each machine's log is under `%USERPROFILE%\nb_os_env\deploy_runtime\<run id>\`
on that machine; failures print the path.

## Blue-green layout

Each booth account keeps two complete installs ("slots"), each with its own
checkout and its own `.venv`. `NB_INSTALL` and `NB_CONFIG` keep their usual
paths, which become links (directory junctions) to the active slot:

```
%USERPROFILE%\
    .neurobooth_os            -> nb_os_env\slots\<active>\config         (NB_CONFIG)
    nb_os_env\
        neurobooth-os         -> slots\<active>\neurobooth-os            (NB_INSTALL)
        configs\                                                         (configs checkout)
        slots\
            state.json         which slot is active, and what each holds
            history.jsonl      deploys and rollbacks (CTR only)
            blue\  neurobooth-os\  config\
            green\ neurobooth-os\  config\
        deploy_runtime\<run id>\
```

Rollback switches the machines of the last deploy back to the slot they came
from — still fully built, so nothing is reinstalled. Each slot's venv is built
at the slot's real path, so a slot never refers to code in the other slot.

The cost is disk: two venvs per account (and staging and Merrimac share
physical machines, so four there).

## First deploy on an existing booth

The machines don't need any preparation beyond what they have today; the
first deploy converts each one:

- The existing checkout at `NB_INSTALL` and the config at `NB_CONFIG` are
  moved into the `blue` slot as-is ("adopted"), the links are created, and the
  new version is built into `green`. Rolling back goes to the adopted install.
  The adopted venv is rebuilt from scratch the next time `blue` is built into.
- Moving the install fails if anything has a handle inside it — close
  terminals, Explorer windows and editors open in `nb_os_env\neurobooth-os` or
  `.neurobooth_os`. `nb_deploy.bat` itself runs from your home directory.

Before the first deploy:

1. **CTR needs `nb_deploy`.** Check out a neurobooth-os commit that contains it
   on CTR the old way (`github_checkout.bat <tag>`). STM and ACQ need nothing:
   CTR copies the deploy agent to them on every run.
2. **Spinnaker wheel path.** For each machine with FLIR devices, add the wheel's
   path *on that machine* to the environment's config in the `configs` repo:
   ```yaml
   machines:
     acq-staging:
       user: TEST_ACQ
       spinnaker_wheel: C:/Users/TEST_ACQ/Downloads/spinnaker_python-4.0.0.116-cp38-cp38-win_amd64.whl
   ```
   The deploy refuses to start without it, since a new venv would otherwise
   have no PySpin.
3. **Existing assumptions, unchanged:** the booth accounts are logged in (the
   tasks use `InteractiveToken`), CTR's `secrets.yaml` has the STM/ACQ
   passwords, the inter-machine setup in
   [inter_machine_setup.md](inter_machine_setup.md) is in place, `uv` and `git`
   are on each account's `PATH`, and the `configs` checkout is at
   `%USERPROFILE%\nb_os_env\configs`.

## How CTR reaches STM and ACQ

The same channel CTR already uses to start the booth servers
(`neurobooth_os/netcomm/client.py`): for each machine it opens an SMB session
to `\\<machine>\C$` as that machine's booth account, copies the agent into
`deploy_runtime\<run id>\`, and runs it via a scheduled task created with
`SCHTASKS /S /U /P` (deleted afterwards). No new ports, services or remote-access
software. Because a CTR account only holds the passwords of its own
environment's accounts, a staging deploy cannot touch the production accounts
that share the machines.

The agent copied to each machine is the one in CTR's *current* install, so a
change to the deploy tool itself takes effect from the deploy after the one
that ships it.

## The old per-machine scripts

`github_checkout.bat` and the `configs` repo's `checkout_and_deploy.bat` chain
still exist for now. Don't use them on a machine that has been switched to the
blue-green layout: they would modify the active slot in place, and `deploy.bat`
deletes and recreates `NB_CONFIG`.

## Recovery

- **A build failed:** nothing was switched. Fix the cause (the failing
  machine's log has it) and rerun; the standby slot is rebuilt.
- **A switch failed partway:** the output says which machines switched. Run
  `nb_deploy rollback` to put them back, or fix the failure and rerun the
  deploy.
- **Adoption was interrupted** (`slots\blue` exists but `nb_os_env\neurobooth-os`
  is still a real directory): look inside `slots\blue`. If it holds the moved
  install, move it back to `nb_os_env\neurobooth-os` (and `slots\blue\config`
  back to `.neurobooth_os`); then delete the empty `slots` directory and rerun.
- **Switching by hand** (if the tool itself is broken), in `cmd` on the machine:
  ```
  rmdir %USERPROFILE%\nb_os_env\neurobooth-os
  mklink /J %USERPROFILE%\nb_os_env\neurobooth-os %USERPROFILE%\nb_os_env\slots\blue\neurobooth-os
  rmdir %USERPROFILE%\.neurobooth_os
  mklink /J %USERPROFILE%\.neurobooth_os %USERPROFILE%\nb_os_env\slots\blue\config
  ```
  `rmdir` on a junction removes only the link. Update `"active"` in
  `slots\state.json` to match.

## Testing without the booths

The deploy code is tested against a simulated three-machine booth
(`tests/pytest/deploy/`): each machine is a temporary home directory in
today's pre-blue-green layout, GitHub is a pair of local bare repos, and `uv`
is a stand-in script. The orchestrator and agent run unmodified. These tests
need only Python, git, pytest, PyYAML and pydantic, so they run on Windows,
macOS and Linux:

```
uv run --no-project --python 3.8 --with pytest --with pyyaml --with pydantic python -m pytest tests/pytest/deploy -o addopts=""
```

- `test_deploy_with_real_uv` builds the venvs with real `uv` (runs when `uv`
  is installed).
- `test_deploy_through_windows_task_scheduler` runs the STM/ACQ agents through
  real Task Scheduler tasks on the local machine. Windows only, and opt-in
  because it creates (and deletes) scheduled tasks: set
  `NB_DEPLOY_TEST_SCHTASKS=1`.

CI (`.github/workflows/tests.yml`) runs these on all three OSes, with the Task
Scheduler test on Windows, plus the full suite on Windows.

**Not covered by the simulation:** the cross-machine login (SMB to `C$` and
`SCHTASKS /S /U /P` with booth credentials). `extras/perf/intermachine_check.py`
validates the SCHTASKS and `admin$` parts of that channel on the booths; `C$`
is the same kind of administrative share but is not checked by it. To exercise it off-site you need a
second Windows machine (a Windows VM is enough) set up per
[inter_machine_setup.md](inter_machine_setup.md). The first real run should be
`nb_deploy --dry-run` on staging.
