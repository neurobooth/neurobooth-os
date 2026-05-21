# LabRecorder v1.17.1 (vendored)

Upstream Windows build of [LabRecorder][upstream] v1.17.1, vendored here to
override `liesl`'s bundled v1.13-b4 binaries. See **#812** for the root cause
(LabRecorderCLI segfaults at XDF finalize due to a 3-year producer/consumer
liblsl version gap) and **#813** for why these files live in the repo
(`uv sync` would otherwise revert the fix every time it ran).

## Contents

| File | Purpose | SHA-256 |
|---|---|---|
| `LabRecorderCLI.exe` | Console recorder spawned by `liesl.Session` | `5a838787c938be19e90a8092c0da436ec7c01dff917b50285ee96b5a851820c5` |
| `lsl.dll`            | liblsl v1.17.5, loaded by the CLI            | `6c97d5456d498ef6a062c74c54ff87cd39efd58dcf67d7bea4b01263d50df445` |
| `LICENSE`            | Upstream MIT license, retained for redistribution compliance | -- |

Upstream zip these were extracted from:
[`LabRecorder-1.17.0-Win_amd64.zip`][upstream-zip], SHA-256
`01bde1d9af07d29de1a8363c967cc1eeaf524915f2db76552484f7becdb161ed`,
published 2026-04-02.

## How they get applied

`extras/perf/upgrade_labrecorder_v1.17.1.ps1` defaults to reading from this
directory (no network required). After every `uv sync` on a booth machine,
re-run:

```powershell
powershell.exe -ExecutionPolicy Bypass `
    -File "$env:NB_INSTALL\extras\perf\upgrade_labrecorder_v1.17.1.ps1"
```

The script is idempotent: it detects pristine, half-applied, and
already-applied states and only modifies the venv when needed.

## Hash verification

`tests/pytest/test_vendored_labrecorder.py` asserts the SHA-256s above on
every test run. If you update these binaries, update the test (and the
hashes in `extras/perf/upgrade_labrecorder_v1.17.1.ps1`) in the same
commit.

[upstream]: https://github.com/labstreaminglayer/App-LabRecorder
[upstream-zip]: https://github.com/labstreaminglayer/App-LabRecorder/releases/download/v1.17.1/LabRecorder-1.17.0-Win_amd64.zip
