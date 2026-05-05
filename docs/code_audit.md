# Neurobooth-OS Code Audit & Quality Assessment

**Date:** March 3, 2026
**Last reviewed:** April 27, 2026
**Scope:** Full codebase audit of [neurobooth-os](https://github.com/neurobooth/neurobooth-os)

---

## Executive Summary

The neurobooth-os project is a Python-based data acquisition and stimulus presentation system for behavioral/physiological research, running across multiple networked Windows machines. This audit covers every top-level folder and configuration file. The codebase has solid domain logic and a reasonable architecture.

Since the initial audit, **all critical security vulnerabilities are resolved** (SQL injection, credentials in code, dynamic-import allowlist), the **device subsystem has been redesigned** to be pluggable (#696, #708 series, #721), **resource lifecycle issues are mostly closed** (SSH tunnel cleanup #663, socket/cursor leaks in usbmux/iPhone/metadator #663, log_sensor_file race fixes #659/#678, EyeLink shutdown crash #688, iPhone listener panic #687, mbient access violation #684), and **a comprehensive hardware-mock infrastructure has landed** (#737, #738) bringing test coverage from effectively zero to 160 unit tests. The XDF stop-recording work is off the GUI thread (#604), all XDF splits are postponed to end-of-day post-processing (#680), and the device-pluggable design lets new devices be added without editing `DeviceManager`/`lsl_streamer.py`/`metadator.py`.

Remaining work focuses on CI hygiene (still no GitHub Actions workflow), the `eval()` calls in `extras/`, two remaining bare `except:` clauses, scattered `BaseException` catches that may mask programmer errors, and the Python 3.8 EOL situation. Packaging is consolidated under uv (#632) -- single `pyproject.toml` + committed `uv.lock`.

### Overall Scores by Area

| Area | Score | Rating |
|------|-------|--------|
| `neurobooth_os/` (core package) | 7/10 | Improved (was 4/10 → 6/10 → 7/10) |
| `extras/` | 3.5/10 | Needs Major Work |
| `examples/` | 5/10 | Improved (was 4/10) |
| `tests/` | 6.5/10 | Improved (was 2.5/10) — 160 tests across 14 files |
| `sql/` | 6/10 | Adequate |
| `eyelink_setup/` | 6/10 | Adequate |
| `docs/` | 7.5/10 | Improved (was 6.5/10) — `testing_with_mocks.md`, expanded `adding_a_device.md`, messaging-architecture assessment |
| CI/CD & Config | 3.5/10 | Needs Work — no progress on workflows |

---

## Table of Contents

1. [neurobooth_os/ (Core Package)](#1-neurobooth_os-core-package)
2. [extras/](#2-extras)
3. [examples/](#3-examples)
4. [tests/](#4-tests)
5. [sql/](#5-sql)
6. [eyelink_setup/](#6-eyelink_setup)
7. [docs/](#7-docs)
8. [CI/CD & Root Configuration](#8-cicd--root-configuration)
9. [Cross-Cutting Concerns](#9-cross-cutting-concerns)
10. [Prioritized Remediation Plan](#10-prioritized-remediation-plan)

---

## 1. neurobooth_os/ (Core Package)

**Files analyzed:** 72 Python files across core modules, tasks, iout, gui, netcomm, and mock subpackages.

### 1.1 ~~Critical: SQL Injection Vulnerabilities~~ RESOLVED

**Resolved in:** PR #582 (`3a9edba`)

All f-string SQL queries in `metadator.py` have been replaced with parameterized queries using `%s` placeholders. Parameter values are passed separately to `.execute()` calls.

### 1.2 ~~Critical: Database Credentials in Code~~ RESOLVED

**Resolved in:** PR #584 (`e78fc15`)

Passwords in `DatabaseSpec` and `ServerSpec` now use Pydantic's `SecretStr` type, preventing accidental exposure in logs, error messages, or repr output. A `secrets.yaml` file pattern has been added to `.gitignore`.

### 1.3 ~~Critical: Dangerous Dynamic Import~~ RESOLVED

**Resolved in:** PR #585 (`735fece`)

`str_fileid_to_eval()` now validates modules against explicit allowlists (`_ALLOWED_MESSAGE_MODULES`, `_ALLOWED_PARSER_MODULES`, `_ALLOWED_TASK_MODULES`, `_ALLOWED_DEVICE_MODULES`) before importing. Blocked attempts are logged.

### 1.4 ~~High: SSH Tunnel Resource Leak~~ RESOLVED

**Resolved in:** PR #663

`SSHTunnelForwarder.start()` is now matched with `tunnel.stop()` in the connection-cleanup path (`metadator.py:122` paired with `metadator.py:141`). PR #663 also fixed socket and cursor leaks in `usbmux`, `iPhone`, and `metadator`.

### 1.5 Medium: Bare and Overly Broad Exception Handlers

Two genuinely bare `except:` clauses remain (down from three at the previous review):

| File | Line | Impact |
|------|------|--------|
| `iout/split_xdf.py` | 299 | Swallows parsing errors silently |
| `iout/usbmux.py` | 28 | Masks connection failures |

The third (`iout/flir_cam.py:198`) was tightened to `except BaseException:` — narrower than fully bare but still too broad. Several other `except BaseException:` clauses exist in `iout/microphone.py`, `iout/mouse_tracker.py`, `iout/webcam.py`, `iout/flir_cam.py`, and the smooth-pursuit graphics module. Some are deliberate (catching C-level OSError leaks from native bindings via `BaseException` rather than `Exception`); the intent should be documented inline so future refactors don't accidentally swallow programmer errors.

**Fix:** For the two remaining bare `except:` clauses, catch specific exception types. For the `BaseException` catches that exist for C-binding error containment, add a comment explaining why the broader catch is necessary.

### 1.6 High: Improper Exception Re-raising

**Location:** `log_manager.py` (line 324; was line 260 before recent log-handler refactors)

```python
raise (e)  # Parentheses just wrap e in a sub-expression — equivalent to `raise e`,
           # but reads ambiguously. The old worry that this constructs a tuple is
           # mistaken (Python doesn't form a 1-tuple without a trailing comma); still
           # worth tightening to `raise` (preserves traceback) for style.
```

Cosmetic / style; demoting from "High" to "Low" but keeping it on the list because it's a one-line fix.

### 1.7 ~~High: Database Connection Leaks~~ MOSTLY RESOLVED

**Mostly resolved in:** PR #663 (cursor leaks) and surrounding work.

`get_database_connection()` still returns a raw `psycopg2` connection without a context manager, but PR #663 audited all call sites and added explicit `cursor.close()` / `connection.close()` paths where they were missing. The remaining design weakness is that a context-managed wrapper would be cleaner than relying on per-callsite discipline; not actively leaking under normal use.

### 1.8 Medium: Excessive Global State -- PARTIALLY RESOLVED

GUI-specific globals have been consolidated into a `SessionState` dataclass (PR #595, `db52c74`). The `gui.py` globals (`running_servers`, `last_task`, `start_pressed`, `session_prepared_count`) are now managed through a `SessionController` that owns a `SessionState` instance.

Remaining globals in other modules:

| File | Globals |
|------|---------|
| `config.py` | `neurobooth_config` |
| `log_manager.py` | `SESSION_ID`, `SUBJECT_ID`, `APP_LOGGER` |
| `server_stm.py` | `calib_instructions`, `frame_preview_device_id` |

### 1.9 ~~Medium: Race Conditions~~ MOSTLY RESOLVED

**Resolved in:** PRs #625 (frame_preview_device_id race + ThreadPoolExecutor timeouts), #659 / #678 (RecordingFiles snapshot race), #686 (database-coordinated log_sensor_file registration).

`frame_preview_device_id` is now properly synchronized and `ThreadPoolExecutor` calls have timeouts. The RecordingFiles-vs-task-snapshot race that was causing files to attach to the wrong task has been fixed both at the immediate symptom (PR #659) and the underlying tagging design (PR #678). One residual concern: there is no automated test for these race conditions; future regressions would have to be caught by manual session testing.

### 1.10 Medium: God Class — PARTIALLY RESOLVED

**Location:** `gui.py`

State management has been extracted into `SessionController` with a `SessionState` dataclass (PR #595). The liesl stop_recording work has been moved off the GUI event loop thread (PR #604). XDF splits are postponed to end-of-day post-processing (PR #680), removing per-task post-recording work from the critical path. The pluggable-device design (PR #696, #708 series, #721) means the GUI/DeviceManager no longer needs per-device case statements when devices are added or removed. However, `gui.py` still handles GUI rendering, messaging, and overall session orchestration in a single file.

### 1.11 Medium: Inconsistent Error Handling Strategy

Functions across the codebase use a mix of: raising exceptions, returning `None` on error, and logging-and-continuing. This makes API contracts unpredictable.

### 1.12 Medium: Code Duplication

`task.py` lines 70-93 contain duplicated code between `present_repeat_instruction_option()` and `present_repeat_task_option()`. The codebase itself acknowledges this with a TODO comment.

### 1.13 Medium: Unexplained Magic Numbers

**Location:** `tasks/task_countdown.py` (line 23)

```python
duration += 2  # "No idea why, but the original code was like this..."
```

### 1.14 Low: Missing Type Hints

Many utility functions in `tasks/utils.py`, `iout/lsl_streamer.py`, and others lack type annotations despite strict mypy being configured in `pyproject.toml`.

### 1.15 Low: 17+ TODO Comments

Unfinished work is documented across the codebase. Notable ones:
- `server_stm.py:326` - "Run this in its own thread"
- `iout/lsl_streamer.py` - Multiple refactoring needs
- `iout/metadator.py:72` - Hardcoded port should be in config

### 1.16 Strengths added since the previous review

The April 2026 work materially improved the core package's structure and testability. Worth calling out as positive findings:

- **Pluggable-device design** (PRs #696, #708 series, #721). New devices are added by writing a `Device` subclass + `DeviceArgs` subclass + a YAML pointing at the `arg_parser`. `DeviceManager` and `lsl_streamer.py` are device-agnostic — capability flags (`STREAM`, `RECORD`, `RECORD_PER_TASK`, `CAMERA_PREVIEW`, `WEARABLE`, `CALIBRATABLE`, `RESETTABLE`, `SESSION_LEVEL`) drive dispatch instead of `isinstance` checks. The `SESSION_LEVEL` capability (PR #721) gates the assigned-but-not-task-referenced bring-up path, fixing the `VidRec_Intel` startup crash from v0.88.0. A 41-test suite (`tests/pytest/test_device_pluggable.py`) verifies the binding registry, hooks, and capability dispatch.

- **Hardware-mock infrastructure** (PRs #737, #738). Six device classes (`Mbient`, `IPhone`, `EyeTracker`, `MicStream`, `VidRec_Flir`, `VidRec_Intel`) have registered mock subclasses in `neurobooth_os/iout/mock/`. Activated at runtime via `NB_MOCK_DEVICES` env var or `mock_devices` config field. Lazy-import refactor (`mbient.py`, `eyelink_tracker.py`, `microphone.py`, `flir_cam.py`, `camera_intel.py`) means those modules import cleanly without `mbientlab` / `pylink` / `pyaudio` / `PySpin` / `pyrealsense2` installed — a hardware-less laptop can run the full unit-test suite. `mock_substitution.py` is a small, well-documented registry; substitution is gated by an empty-targets check so production behavior is unchanged when no mocks are configured. Operator-facing reference at `docs/testing_with_mocks.md`; architectural reference in `docs/arch/adding_a_device.md`.

- **Crash and resource hardening**: faulthandler crash logging (PR #613), system resource logging (PR #614), startup error fallback logging (PR #588), atomic writes for `server_pids.txt` (PR #592), graceful handling of stale PID-file entries (PR #607), full traceback on STM task-loop exceptions before re-raising, increased recursion limit in STM error handler to survive RecursionError under PsychoPy load.

- **Inter-task critical path** (PRs #594, #605, #611, #598, #589, #604, #680): camera start parallelized in DeviceManager, task instances pre-constructed during welcome screen, `StopRecording` + `StartRecording` combined into `TransitionRecording`, timing instrumentation added, STM message polling intervals reduced, liesl `stop_recording` moved off the GUI thread, all XDF splits postponed to end-of-day post-processing.

### Module-by-Module Summary

| Module | Severity | Key Issues | Status |
|--------|----------|------------|--------|
| `iout/metadator.py` | ~~CRITICAL~~ MEDIUM | ~~SQL injection~~, SSH tunnel leak, ~~swallowed exceptions~~ | SQL injection + import whitelist fixed |
| `config.py` | ~~HIGH~~ LOW | ~~Credentials in code~~, permissive globals | SecretStr applied |
| `gui.py` | ~~HIGH~~ MEDIUM | ~~God class~~ partially refactored, threading improved | SessionState + threading fixes |
| `log_manager.py` | MEDIUM | Global state abuse, exception handling | Faulthandler + fallback logging added |
| `server_stm.py` | MEDIUM | Race conditions, incomplete TODOs | -- |
| `iout/lsl_streamer.py` | MEDIUM | Module-level side effects, design inconsistencies | -- |
| `iout/mbient.py` | MEDIUM | Thread/process mixing | -- |
| `iout/split_xdf.py` | MEDIUM | Bare except, unsafe parsing | -- |
| `netcomm/client.py` | ~~MEDIUM~~ LOW | ~~Non-atomic file operations~~ | Atomic writes implemented |
| `tasks/task_basic.py` | MEDIUM | Many TODOs, no cleanup guarantees on exception | -- |
| `iout/eyelink_tracker.py` | LOW | Missing type hints | Updated (#587) |
| `tasks/utils.py` | LOW | Missing type hints, doc gaps | -- |

---

## 2. extras/

**Files analyzed:** 34 Python scripts + 5 JSON configuration files. These are development/utility scripts for device testing, data processing, and analysis.

### 2.1 Critical: Unsafe `eval()` Usage

**5 instances** across multiple files:

| File | Line |
|------|------|
| `intel_body_landmarks.py` | 109-110 |
| `convert_bag2vid_timestamps.py` | 36-37 |
| `synch_frame_mean_rgb.py` | 61-62 |

```python
size_depth = eval(intel_lsl["info"]["desc"][0]["size_depth"][0])
```

If HDF5 data is compromised, this allows arbitrary code execution.

**Fix:** Replace with `ast.literal_eval()`.

### 2.2 High: Bare Exception Clauses

| File | Line | Pattern |
|------|------|---------|
| `synch_frame_mean_rgb.py` | 202 | `except:` swallows all errors |
| `synch_frame_mean_rgb_flir_iphone.py` | 183 | `except:` swallows all errors |

### 2.3 High: Database Error Handling Bug

**Location:** `add_subject.py` (lines 195-196)

```python
except Exception as e:
    sg.popup_error("Database insert failed:", str(e))
return True  # Returns success DESPITE the exception!
```

This allows corrupt data entry to appear successful.

### 2.4 High: Massive Code Duplication

| Duplicated Pair | Overlap |
|----------------|---------|
| `connect.py` / `connect2.py` | ~100% (only author differs) |
| `mbients_connect_rec_directly.py` / `mbients_connect_rec_directly_acc.py` | ~95% |
| `synch_frame_mean_rgb.py` / `synch_frame_mean_rgb_flir_iphone.py` | ~80% |
| `convert_bag2vid_timestamps.py` / `intel_body_landmarks.py` | Substantial (`convert_bag_2_avi`) |
| `clapping_test_plotting.py` / `plot_timing_test_sync.py` | Shared helper functions |

### 2.5 Medium: Hardcoded Device Credentials

**Location:** `mbients_connect_rec_directly.py` (lines 90-96)

```python
mbients = {
    "LF": "DA:B0:96:E4:7F:A3",
    "LH": "E8:95:D6:F7:39:D2",
    ...
}
```

MAC addresses and 20+ hardcoded `Z:\` drive paths should be externalized to config.

### 2.6 Medium: Infinite Loop Without Exit

**Location:** `network_conn_check.py` (lines 24-34)

```python
while True:
    for node in nodes:
        out = subprocess.run(["ping", node], stdout=subprocess.PIPE)
    # time.sleep(10)  <- commented out!
```

No exit condition and no sleep between iterations.

### 2.7 Medium: Deprecated API Usage

**Location:** `plot_timing_test_sync.py` (line 6)

Uses `optparse.OptionParser` (deprecated since Python 2.7). Should use `argparse`.

### 2.8 Medium: Resource Leaks

`cv2.VideoCapture` objects in `intel_body_landmarks.py` and `convert_bag2vid_timestamps.py` are opened but have no `try/finally` to ensure `cap.release()` on exception.

### 2.9 Low: 19 Files with No Docstrings

The vast majority of scripts have zero documentation. Only `reset_mbients.py`, `dump_iphone_video.py`, and `relabel_subject_id.py` serve as positive examples.

### 2.10 Low: Misspelled Filename

`threding_timestamps.py` should be `threading_timestamps.py`. This file also references undefined imports (`monitors`, `visual`).

### Per-File Quality Ratings

| Rating | Files |
|--------|-------|
| HIGH quality | `dump_iphone_video.py`, `relabel_subject_id.py`, `reset_mbients.py`, `plot_system_performance.py` |
| MEDIUM quality | `add_subject.py`, `cleanup_bag_files.py`, `see_cam.py`, `time_clocks.py`, `time_clocks_variance.py` |
| LOW quality | `connect.py`, `connect2.py`, `mbients_connect_rec_directly*.py`, `network_conn_check.py`, `plot_eyelink_lsl_edf.py`, `synch_frame_mean_rgb*.py`, `threding_timestamps.py`, `run_xdf_split_postproces.py` |

---

## 3. examples/

**Files analyzed:** 1 Python file, 1 Jupyter notebook, 1 batch file, 2 YAML configs, ~200 configuration/asset files in `configs/` subdirectories. *(Note: `environments/` directory with hardcoded credentials was removed in PR #590.)*

### 3.1 ~~High: Hardcoded Credentials in Config~~ RESOLVED

**Resolved in:** PR #590 (`5e2062b`)

The `environments/` directory containing `neurobooth_os_config.json` with hardcoded credentials has been removed from the repository.

### 3.2 High: Jupyter Notebook Runtime Errors

**Location:** `Neurobooth_data_visualizer.ipynb`

Multiple unresolved errors in notebook output cells:
- `NameError: name 'tstamp' is not defined` -- variable not initialized on all code paths
- `IndexError: index 0 is out of bounds` -- no array shape validation
- Hardcoded path: `C:\neurobooth\neurobooth_data`
- Resource leaks: `cv2.VideoCapture` and `pyaudio.PyAudio` objects not cleaned up on exception

### 3.3 Medium: Example Out of Date with Codebase

**Location:** `eye_tracking.py`

- No error handling, logging, or type hints (main codebase has all three)
- `EyeTracker.__init__` in the real code requires `device_args` parameter not shown
- Missing `marker_outlet` and `with_lsl` parameters used in production
- No context managers or resource cleanup

### 3.4 Medium: DRY Violation in Config

**Location:** `split_task_device_map.yml` (388 lines)

Massive repetition of identical device lists across tasks. Could be reduced ~70% using YAML anchors/aliases.

### 3.5 ~~Low: Batch Script Issues~~ RESOLVED

**Resolved by:** uv migration (#632) -- `set_conda_env.bat` removed entirely. The new install path is documented in `README.md` and uses `uv sync` (no manual `pause`/wheel-path/yml-name issues).

### 3.6 Low: Non-Descriptive Config File Names

Instruction files under `configs/instructions/` are named by number only (`1.yml`, `9.yml`, `10.yml`). No way to know what each instruction is without opening the file.

---

## 4. tests/

**Files analyzed:** 14 test files (12 in `tests/pytest/`, 2 in `neurobooth_os/iout/tests/`), totalling 160 collected unit tests as of v0.89.0.

### 4.1 ~~Critical: Near-Zero Test Coverage~~ MAJOR IMPROVEMENT

The previous review reported "effectively 1 test" (a one-line `import_test.py`). The current suite:

| File | Tests | Focus |
|------|------:|-------|
| `tests/pytest/test_device_pluggable.py` | 41 | Pluggable-device registry, hooks, capability dispatch |
| `tests/pytest/test_device_lifecycle.py` | 17 | `Device` base-class lifecycle |
| `tests/pytest/test_mock_substitution.py` | 17 | Mock-substitution mechanism + lazy-import smoke tests |
| `neurobooth_os/iout/tests/test_db_connection.py` | 14 | DB connection helpers |
| `tests/pytest/test_mock_mbient.py` | 11 | MockMbient lifecycle |
| `tests/pytest/test_mock_iphone.py` | 9 | MockIPhone lifecycle (handshake, recording, frame_preview) |
| `tests/pytest/test_mock_intel.py` | 8 | MockVidRec_Intel lifecycle |
| `tests/pytest/test_mock_eyetracker.py` | 8 | MockEyeTracker lifecycle |
| `neurobooth_os/iout/tests/test_metadator.py` | 7 | Metadator helpers (some still DB-dependent) |
| `tests/pytest/test_gui_single_instance.py` | 7 | Single-instance gating (PR #510) |
| `tests/pytest/test_xdf_backlog.py` | 6 | XDF backlog post-processing |
| `tests/pytest/test_mock_flir.py` | 6 | MockVidRec_Flir lifecycle |
| `tests/pytest/test_mock_microphone.py` | 6 | MockMicStream lifecycle |
| `tests/pytest/test_video_files_race.py` | 3 | Recording-files race regression |

The mock infrastructure (PRs #737, #738) is the biggest lift: tests run on a hardware-less laptop without `mbientlab`, `pylink`, `pyaudio`, `PySpin`, or `pyrealsense2` installed. Each device mock has a sibling test module that exercises bring-up → start → stop → close, plus device-specific paths (LSL sample shape, frame_preview bytes, stub file write, etc.).

### 4.2 Medium: Test Suite Stability on Windows

`pytest` over the full suite intermittently segfaults at process shutdown on Windows after C-extension teardown (`pyrealsense2` / `pyaudio` / `pylsl`). Per-file invocation completes cleanly. This is a Windows-and-C-extension issue, not a test-logic problem; flagged because it precludes a single-command "all tests pass" check until resolved. Workarounds: run one test file at a time, or use `pytest --forked` with the `pytest-forked` plugin.

### 4.3 ~~Medium: `tox.ini` Test Paths Still Out of Sync~~ RESOLVED

**Resolved by:** removing `tox.ini`. The project targets a single Python version (3.8) and has no GitHub Actions workflow, so tox's matrix value didn't apply. Tests are now invoked directly via `pytest`.

### 4.4 Medium: No CI Integration

`.github/workflows/` does not exist. The 160 tests have to be run manually. Adding a workflow that runs `pytest tests/pytest/ neurobooth_os/iout/tests/ --no-cov` per file (sidestepping the segfault issue) on push/PR would significantly increase confidence in changes touching the device subsystem, where the test coverage is now substantial.

### 4.5 ~~Low: Deployment-test Batch Scripts Still Hardcoded~~ RESOLVED

**Resolved by:** uv migration (#632) -- `tests/deployment-test/run_timing_tests*.bat` now activate `%NB_INSTALL%\.venv\Scripts\activate.bat` instead of the hardcoded `C:\Users\CTR\anaconda3` path. Same fix applied to `extras/reset_mbients.bat` and `extras/serv_acq_upload - neurobooth_OS.bat`.

---

## 5. sql/

**Files analyzed:** 2 SQL files.

### 5.1 Strengths

- Proper role-based access control (RBAC): ownership assigned to `neuroboother`, read-only grants to `neurovisualizer`
- `IF NOT EXISTS` clauses for idempotent migrations
- Clear version tracking (v0.55.0, v0.56.0)
- Sensible data types (timestamp with time zone, character varying, date)

### 5.2 Concerns

- **No rollback scripts** -- only forward migrations exist
- **No foreign key constraints visible** in the schema files
- **No row-level security (RLS) policies**
- **No column-level comments** for documentation
- **Very limited migration history** -- only 2 files for what appears to be a production system
- **No data retention policies** -- tables could grow unbounded

---

## 6. eyelink_setup/

**Files analyzed:** README.md, `start_tk_new` shell script (907 lines), network diagrams.

### 6.1 Strengths

- Excellent documentation with step-by-step instructions and network diagrams
- Robust input validation: IP addresses validated with regex, netmasks validated, WiFi passphrases checked for 8-64 characters
- Proper network isolation (breaks internal bridge between WiFi/Ethernet NICs)
- Graceful fallbacks to default values

### 6.2 Medium: Hardcoded Default WiFi Password

```sh
WIFI_PASSPHRASE=eyelink3  # Factory default -- trivially guessable
```

Uses WPA-PSK instead of WPA2-Enterprise. Passphrase stored in plaintext in config files. No documentation warning to change the default.

### 6.3 Low: File Permissions Not Enforced

The script creates config files but doesn't set restrictive permissions (`chmod 600`) on sensitive files like `netconfig.ini`.

---

## 7. docs/

**Files analyzed:** 12 files (Sphinx config, RST pages, markdown guides, plaintext instructions).

### 7.1 Strengths

- `system_architecture.md` -- Excellent. Clear service descriptions (CTR, STM, ACQ), device assignment tables, message routing, config schema with JSON examples.
- `system_configuration.md` -- Good. Separation of config vs. code, environment variable setup, cross-references to examples.
- `single_machine_testing.md` -- Good. Prerequisites, step-by-step config changes, database setup, PyCharm debugging tips.

### 7.2 Documentation Gaps

| Missing Documentation | Priority |
|----------------------|----------|
| Release process (file exists but content unclear) | HIGH |
| CI/CD pipeline | HIGH |
| Deployment procedures | HIGH |
| Troubleshooting guide | HIGH |
| Security/secrets management | HIGH |
| API documentation (only 3 auto-generated stubs in `api.rst`) | MEDIUM |
| Database schema documentation | MEDIUM |
| Architecture diagrams | LOW |

### 7.3 Outdated Content

`instructions_mbient_install.txt` references `conda create -n neurobooth python=3.8 ... -c conda-forge/label/cf202003` -- the channel label may no longer be available and Python 3.8 is EOL.

---

## 8. CI/CD & Root Configuration

### 8.1 Critical: No CI/CD Workflows

`.github/workflows/` directory does not exist. There is no automated testing, linting, coverage reporting, or deployment automation.

### 8.2 ~~Critical: Missing `requirements_dev.txt`~~ RESOLVED

**Resolved by:** uv migration (#632). Developer dependencies now live in
`pyproject.toml` under `[dependency-groups] dev` (PEP 735) and install with
`uv sync --group dev`. `contributing.rst` updated.

### 8.3 ~~High: `setup.py` Lists Only One Dependency~~ RESOLVED

**Resolved by:** uv migration (#632). `setup.py` and
`environment_staging.yml` are gone; `pyproject.toml`'s `[project.dependencies]`
is the single source of truth, with `uv.lock` pinning exact versions for
reproducible installs across booth machines.

### 8.4 ~~High: `github_checkout.bat` Generates Invalid Python~~ NOT REPRODUCIBLE

The version-stamping logic now lives in `configs/version.bat` (the `github_checkout.bat` script just calls `git checkout <tag>`). `version.bat` writes `neurobooth_os/current_config.py` with this template:

```batch
(
    echo.
    echo.
    echo """
    echo     Stores neurobooth config version number.
    echo     GENERATED FILE. DO NOT EDIT MANUALLY
    echo """
    echo.
    echo version = '%TAG%'
) > "%TAG_FILE%"
```

The actual output IS valid Python — the triple-quoted lines start and close a module docstring. Either the audit was incorrect on this point or the script was rewritten after the previous review. Verified `current_config.py` on master imports cleanly (`from neurobooth_os.current_config import version` returns `'NO VERSION SET'`).

PR #741 (in flight at audit time) drops the unrelated stale `__version__ = "0.0.54.0"` from `__init__.py` and points `setup.py` at `current_config.py:version` so `pip install` reads the same source-of-truth that deploy stamps.

### 8.5 ~~High: `tox.ini` Test Paths Out of Sync~~ RESOLVED

**Resolved by:** removing `tox.ini` (see §4.3).

### 8.6 Medium: Python 3.8 Only

`pyproject.toml` pins `requires-python = ">=3.8,<3.9"`. Python 3.8 reached end-of-life in October 2024. The Python upgrade is tracked in #682 and is intentionally deferred until after the uv migration (#632) lands so the two changes don't compound.

### 8.7 Medium: `.gitignore` Missing Common Patterns

Missing `.pytest_cache/` and `.mypy_cache/` patterns.

### 8.8 ~~Low: Deprecated `distutils` Import in `setup.py`~~ RESOLVED

**Resolved by:** uv migration (#632) -- `setup.py` removed entirely.

---

## 9. Cross-Cutting Concerns

### 9.1 Security Summary

| Issue | Severity | Location | Status |
|-------|----------|----------|--------|
| SQL injection via f-strings | ~~CRITICAL~~ | `iout/metadator.py` | RESOLVED (PR #582) |
| `eval()` on HDF5 data | CRITICAL | 5 instances across 4 files in `extras/` | OPEN |
| Dynamic import without whitelist | ~~HIGH~~ | `iout/metadator.py` | RESOLVED (PR #585) |
| Credentials in config/code | ~~HIGH~~ | `config.py`, `examples/`, `extras/perf/` | RESOLVED (PRs #584, #590, perf-credentials cleanup 2026-04-14) |
| SSH tunnel never closed | ~~HIGH~~ | `iout/metadator.py` | RESOLVED (PR #663) |
| Default WiFi password "eyelink3" | MEDIUM | `eyelink_setup/` | OPEN |
| Hardcoded MAC addresses | MEDIUM | `extras/` | OPEN |
| Plaintext secrets in config files | ~~MEDIUM~~ | Multiple | RESOLVED (SecretStr + secrets.yaml + git-ignored db_credentials.json) |

### 9.2 ~~Dependency Management~~ RESOLVED

**Resolved by:** uv migration (#632). All runtime dependencies live in
`pyproject.toml` under `[project.dependencies]`; dev tooling lives in
`[dependency-groups] dev`. `uv.lock` pins exact versions across booth
machines. `setup.py` and `environment_staging.yml` removed.

### 9.3 Logging Inconsistency

- Core package: Uses `logging.getLogger(APP_LOG_NAME)` (good)
- Extras: Mix of `print()` statements and no logging at all
- 3 extras files have proper logging (positive examples)
- No centralized logging configuration

### 9.4 Type Safety

`pyproject.toml` configures strict mypy settings, but type hints are absent from the majority of the codebase, meaning the configuration is largely unenforced.

---

## 10. Prioritized Remediation Plan

### Phase 1: Critical Security & Stability (Immediate)

1. ~~**Fix SQL injection** in `metadator.py`~~ — DONE (PR #582)
2. **Replace `eval()`** with `ast.literal_eval()` in 5 extras files — STILL OPEN
3. ~~**Add `tunnel.stop()` calls** for SSH tunnel cleanup~~ — DONE (PR #663)
4. ~~**Remove hardcoded credentials**~~ — DONE (PRs #584 SecretStr, #590 removed example configs, perf-credentials cleanup 2026-04-14)
5. ~~**Create `requirements_dev.txt`** so developers can onboard~~ — DONE (#632 uv migration; dev deps now in `[dependency-groups] dev`)
6. ~~**Fix `github_checkout.bat`** Python file generation syntax~~ — NOT REPRODUCIBLE on current code; `version.bat` produces valid Python (see §8.4)

### Phase 2: Testing & CI (Weeks 1-2)

7. Create `.github/workflows/tests.yml` for automated testing on push/PR — STILL OPEN
8. ~~Write unit tests for core modules~~ — LARGELY DONE: 160 tests across 14 files (was effectively 1). Mock-device infrastructure (#737, #738) lets the suite run on a hardware-less laptop. Coverage now meaningful for `Device` lifecycle, pluggable-device registry, mock substitution, mock device behaviour, log_sensor_file race regressions.
9. ~~Fix `tox.ini` test paths to match actual file locations~~ — DONE: `tox.ini` removed (single-Python-version project with no CI workflow doesn't benefit from tox)
10. Add database mocking to `test_metadator.py` — STILL OPEN; new `test_db_connection.py` is mostly DB-mocked but `test_metadator.py` still requires a live DB
11. ~~Add `setup.py` dependencies to match actual requirements~~ — DONE (#632 uv migration; `setup.py` removed, deps consolidated in `pyproject.toml`)
12. Fix bare `except:` clauses — PARTIALLY DONE: down from 3 to 2 (`flir_cam.py:198` was tightened; `split_xdf.py:299` and `usbmux.py:28` remain bare)

### Phase 3: Code Quality (Weeks 3-4)

13. Consolidate duplicated extras files (5 pairs identified)
14. ~~Refactor `gui.py` into separate concerns~~ -- PARTIALLY DONE (PR #595 SessionState dataclass, PR #604 moved liesl off GUI thread)
15. ~~Replace global mutable state with dependency injection or singletons~~ -- PARTIALLY DONE (PR #595 consolidated GUI state)
16. Add type hints to all public APIs
17. Fix the `raise (e)` syntax in `log_manager.py`
18. Add context managers for database connections
19. Fix `add_subject.py` returning `True` after database errors

### Phase 4: Documentation & Maintenance (Weeks 5-6)

20. Write release process documentation
21. Create troubleshooting guide
22. Update `eye_tracking.py` example to match current API
23. Fix Jupyter notebook errors and remove hardcoded paths
24. Add security configuration documentation
25. Update Mbient installation instructions for current Python versions
26. Add column-level comments to SQL schema
27. Update Python version targets (3.9+ minimum)

### Phase 5: Long-Term Improvements

28. ~~Implement async database operations for GUI responsiveness~~ -- PARTIALLY DONE (PR #604 moved liesl stop_recording off GUI thread)
29. Add comprehensive API documentation with usage examples
30. Create SQL migration rollback scripts
31. Add code coverage thresholds to CI pipeline
32. Consider WPA2-Enterprise for EyeLink WiFi
33. Add automated security scanning to CI/CD

### Additional Improvements (completed since initial audit)

34. ~~Add faulthandler crash logging~~ — DONE (PR #613)
35. ~~Add system resource logging to GUI process~~ — DONE (PR #614)
36. ~~Add startup error fallback logging~~ — DONE (PR #588)
37. ~~Use atomic writes for server_pids.txt~~ — DONE (PR #592)
38. ~~Add module allowlist to dynamic imports~~ — DONE (PR #585)
39. ~~Replace ipython with python in server bat files~~ — DONE (PR #578)
40. ~~Switch config loader from JSON to YAML~~ — DONE (PR #574)
41. ~~Add pytest to environment_staging.yml~~ — DONE (PR #586)
42. ~~Fix dump_iphone_video crash with multiple acquisition servers~~ — DONE (PR #580)
43. ~~Handle stale entries in server_pids.txt gracefully~~ — DONE (PR #607)
44. ~~Parallelize camera start in DeviceManager~~ — DONE (PR #594)
45. ~~Pre-construct task instances during welcome screen~~ — DONE (PR #605)
46. ~~Combine StopRecording + StartRecording into TransitionRecording~~ — DONE (PR #611)
47. ~~Add timing instrumentation to inter-task critical path~~ — DONE (PR #598)
48. ~~Reduce STM message polling intervals~~ — DONE (PR #589)
49. ~~Resource leaks in usbmux/iPhone/metadator~~ — DONE (PR #663)
50. ~~Pluggable device registration~~ — DONE (PR #696)
51. ~~Retire device_start_function / DeviceArgs.instance_device_class / legacy marker_stream / CameraPreviewer~~ — DONE (#708 series)
52. ~~Add MouseDeviceArgs, marker as a config-driven Device~~ — DONE (#708 series)
53. ~~Gate session-level device discovery on SESSION_LEVEL capability~~ — DONE (PR #721, fixes v0.88.0 acquisition crash)
54. ~~Mock-device substitution mechanism + lazy hardware imports~~ — DONE (PR #737)
55. ~~Mocks for Mbient, IPhone, EyeTracker, MicStream, VidRec_Flir, VidRec_Intel~~ — DONE (PRs #737, #738)
56. ~~Operator-facing testing-with-mocks doc + arch/adding_a_device "Running with mocks" subsection~~ — DONE (PRs #737, #738)
57. ~~Bound DSC._wait_release with a 2s timeout~~ — DONE (PR #740, fixes PsychoPy keyboard-drop wedge under camera load)
58. ~~Auto-focus subject_id input on GUI startup~~ — DONE (PR #739)
59. ~~Postpone all XDF splits to end-of-day post-processing~~ — DONE (PR #680)
60. ~~Database-coordinated log_sensor_file registration~~ — DONE (PR #686)
61. ~~RecordingFiles snapshot race fixes~~ — DONE (PRs #659, #678)
62. ~~Prevent EyeTracker shutdown crash when EyeLink failed to connect~~ — DONE (PR #688)
63. ~~Suppress iPhone listener panic during shutdown~~ — DONE (PR #687)
64. ~~Mbient access violation during reset, harden iPhone listener~~ — DONE (PR #684)
65. ~~Frame_preview_device_id race + ThreadPoolExecutor timeouts~~ — DONE (PR #625)
66. ~~Single-instance gui.py guard~~ — DONE (PR #510)
67. ~~Config normalization (machines + services)~~ — DONE (PRs #597, #662, #035f376)
68. ~~Move crash and startup logs to local_log_dir~~ — DONE (PR #673)
69. ~~Drop stale `__version__` from `__init__.py`; setup.py reads `current_config.py`~~ — DONE (PR #741)
70. ~~Migrate from conda to uv; consolidate dependencies into `pyproject.toml`~~ — DONE (#632)
