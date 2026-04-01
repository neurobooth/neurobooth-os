# Neurobooth-OS Code Audit & Quality Assessment

**Date:** March 3, 2026
**Last reviewed:** April 1, 2026
**Scope:** Full codebase audit of [neurobooth-os](https://github.com/neurobooth/neurobooth-os)

---

## Executive Summary

The neurobooth-os project is a Python-based data acquisition and stimulus presentation system for behavioral/physiological research, running across multiple networked Windows machines. This audit covers every top-level folder and configuration file. The codebase has solid domain logic and a reasonable architecture.

Since the initial audit, **all critical security vulnerabilities have been resolved**: SQL injection has been fixed with parameterized queries, credentials are protected with `SecretStr`, and dynamic imports are gated by a module allowlist. GUI state has been refactored into a `SessionState` dataclass, file operations are now atomic, logging has been significantly improved (faulthandler crash logging, system resource logging, startup error fallback logging), and example configs with hardcoded credentials have been removed. Remaining work focuses on resource lifecycle management (SSH tunnel leak, database connection cleanup), bare exception handlers, test coverage, and CI/CD automation.

### Overall Scores by Area

| Area | Score | Rating |
|------|-------|--------|
| `neurobooth_os/` (core package) | 6/10 | Improved (was 4/10) |
| `extras/` | 3.5/10 | Needs Major Work |
| `examples/` | 5/10 | Improved (was 4/10) |
| `tests/` | 2.5/10 | Critical |
| `sql/` | 6/10 | Adequate |
| `eyelink_setup/` | 6/10 | Adequate |
| `docs/` | 6.5/10 | Fair |
| CI/CD & Config | 3.5/10 | Needs Work (was 3/10) |

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

### 1.4 High: SSH Tunnel Resource Leak

**Location:** `neurobooth_os/iout/metadator.py` (lines 66-74)

`SSHTunnelForwarder.start()` is called but `tunnel.stop()` is never called anywhere in the codebase. This leaks tunnel resources indefinitely.

### 1.5 High: Bare Exception Handlers

Multiple files catch all exceptions indiscriminately:

| File | Line | Impact |
|------|------|--------|
| `iout/flir_cam.py` | 198 | Catches KeyboardInterrupt/SystemExit |
| `iout/split_xdf.py` | 247 | Swallows parsing errors silently |
| `iout/usbmux.py` | 28 | Masks connection failures |

**Fix:** Catch specific exception types (e.g., `except Exception as e:`).

### 1.6 High: Improper Exception Re-raising

**Location:** `log_manager.py` (line 260)

```python
raise (e)  # Parentheses create a tuple -- should be: raise e
```

### 1.7 High: Database Connection Leaks

**Location:** `iout/metadator.py` (lines 62-90)

`get_database_connection()` returns a raw `psycopg2` connection without a context manager. Many callers don't close connections explicitly, leading to potential connection pool exhaustion.

### 1.8 Medium: Excessive Global State -- PARTIALLY RESOLVED

GUI-specific globals have been consolidated into a `SessionState` dataclass (PR #595, `db52c74`). The `gui.py` globals (`running_servers`, `last_task`, `start_pressed`, `session_prepared_count`) are now managed through a `SessionController` that owns a `SessionState` instance.

Remaining globals in other modules:

| File | Globals |
|------|---------|
| `config.py` | `neurobooth_config` |
| `log_manager.py` | `SESSION_ID`, `SUBJECT_ID`, `APP_LOGGER` |
| `server_stm.py` | `calib_instructions`, `frame_preview_device_id` |

### 1.9 Medium: Race Conditions

**Location:** `server_stm.py` (line 57)

`frame_preview_device_id` is accessed from multiple threads without synchronization. Also, `ThreadPoolExecutor` calls use `concurrent.futures.wait()` without a timeout, risking indefinite hangs.

### 1.10 Medium: God Class -- PARTIALLY RESOLVED

**Location:** `gui.py`

State management has been extracted into `SessionController` with a `SessionState` dataclass (PR #595). The liesl stop_recording work has been moved off the GUI event loop thread (PR #604). However, `gui.py` still handles GUI rendering, messaging, and device management in a single file.

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

### 3.5 Low: Batch Script Issues

**Location:** `set_conda_env.bat`

- No error checking after conda commands
- Hardcoded wheel path: `c:\spinnaker\spinnaker_python-3.1.0.79-cp38-cp38-win_amd64.whl`
- Uses `pause` for manual intervention instead of automated error handling
- References `environment_staging.yml` but actual file may be `environment.yml`

### 3.6 Low: Non-Descriptive Config File Names

Instruction files under `configs/instructions/` are named by number only (`1.yml`, `9.yml`, `10.yml`). No way to know what each instruction is without opening the file.

---

## 4. tests/

**Files analyzed:** 3 test files total.

### 4.1 Critical: Near-Zero Test Coverage

The entire test suite consists of:

| File | Content |
|------|---------|
| `tests/pytest/import_test.py` | `import neurobooth_os` (1 line) |
| `tests/deployment-test/run_timing_tests.bat` | Batch script with hardcoded paths to `C:\Users\CTR\` |
| `tests/deployment-test/run_timing_tests_plotting.bat` | Batch script with hardcoded paths |
| `neurobooth_os/iout/tests/test_metadator.py` | Database-dependent test (requires live DB, no mocking) |

For a 72-file package, this is critically insufficient.

### 4.2 High: Tests Are Not Portable -- PARTIALLY RESOLVED

Batch test scripts hardcode paths like `C:\Users\CTR\anaconda3\Scripts\activate.bat`. The `ipython` usage in server batch files has been replaced with `python` (PR #578), but test-specific batch scripts still use hardcoded paths.

### 4.3 High: No Test Framework Integration

- `tox.ini` references test paths that don't exist (`neurobooth_os/netcomm/tests/test_server.py`)
- No pytest fixtures, conftest.py, or proper test structure
- No mocking of database or device dependencies

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

**Files analyzed:** README.rst, `start_tk_new` shell script (907 lines), network diagrams.

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

`.github/workflows/` directory does not exist. There is no automated testing, linting, coverage reporting, or deployment automation. `tox.ini` exists but has no pipeline to run it.

### 8.2 Critical: Missing `requirements_dev.txt`

`tox.ini` references `requirements_dev.txt` and `contributing.rst` tells developers to `pip install -r requirements_dev.txt`, but the file does not exist in the repository. This blocks developer onboarding.

### 8.3 High: `setup.py` Lists Only One Dependency

```python
install_requires=['pandas']
```

The project requires 160+ packages (documented in `environment_staging.yml`) but `pip install neurobooth-os` would only install pandas, leading to immediate ImportErrors.

### 8.4 High: `github_checkout.bat` Generates Invalid Python

The batch file creates `neurobooth_os/current_release.py` with broken syntax:

```batch
echo """
echo     Stores neurobooth version number.
echo """
echo version = '%TAG%'
```

This produces invalid Python (triple-quotes as separate echo lines).

### 8.5 High: `tox.ini` Test Paths Out of Sync

```ini
commands =
    pytest --cov=neurobooth_os neurobooth_os/netcomm/tests/test_server.py  # doesn't exist
    pytest --cov=neurobooth_os neurobooth_os/tests/                        # doesn't exist
```

Actual test files are at `tests/pytest/` and `neurobooth_os/iout/tests/`.

### 8.6 Medium: Python 3.8 Only

`tox.ini` and `environment_staging.yml` target Python 3.8.18, which reached end-of-life in October 2024. No support for Python 3.9+.

### 8.7 Medium: `.gitignore` Missing Common Patterns

Missing `.pytest_cache/` and `.mypy_cache/` patterns.

### 8.8 Low: Deprecated `distutils` Import in `setup.py`

Uses `from distutils.command.sdist import sdist` which is deprecated and removed in Python 3.12.

---

## 9. Cross-Cutting Concerns

### 9.1 Security Summary

| Issue | Severity | Location | Status |
|-------|----------|----------|--------|
| SQL injection via f-strings | ~~CRITICAL~~ | `iout/metadator.py` | RESOLVED (PR #582) |
| `eval()` on HDF5 data | CRITICAL | 5 files in `extras/` | OPEN |
| Dynamic import without whitelist | ~~HIGH~~ | `iout/metadator.py` | RESOLVED (PR #585) |
| Credentials in config/code | ~~HIGH~~ | `config.py`, `examples/` | RESOLVED (PRs #584, #590) |
| SSH tunnel never closed | HIGH | `iout/metadator.py` | OPEN |
| Default WiFi password "eyelink3" | MEDIUM | `eyelink_setup/` | OPEN |
| Hardcoded MAC addresses | MEDIUM | `extras/` | OPEN |
| Plaintext secrets in config files | ~~MEDIUM~~ | Multiple | RESOLVED (SecretStr + secrets.yaml) |

### 9.2 Dependency Management

Dependencies are fractured across three sources with no consistency:

| Source | Dependencies Listed |
|--------|-------------------|
| `setup.py` | 1 (pandas) |
| `environment_staging.yml` | 160+ |
| `requirements_dev.txt` | Missing entirely |

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

1. ~~**Fix SQL injection** in `metadator.py`~~ -- DONE (PR #582)
2. **Replace `eval()`** with `ast.literal_eval()` in 5 extras files
3. **Add `tunnel.stop()` calls** for SSH tunnel cleanup
4. ~~**Remove hardcoded credentials**~~ -- DONE (PRs #584 SecretStr, #590 removed example configs)
5. **Create `requirements_dev.txt`** so developers can onboard
6. **Fix `github_checkout.bat`** Python file generation syntax

### Phase 2: Testing & CI (Weeks 1-2)

7. Create `.github/workflows/tests.yml` for automated testing on push/PR
8. Write unit tests for core modules (target 50% coverage as a start)
9. Fix `tox.ini` test paths to match actual file locations
10. Add database mocking to `test_metadator.py`
11. Add `setup.py` dependencies to match actual requirements
12. Fix bare `except:` clauses (specify exception types)

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

34. ~~Add faulthandler crash logging~~ -- DONE (PR #613)
35. ~~Add system resource logging to GUI process~~ -- DONE (PR #614)
36. ~~Add startup error fallback logging~~ -- DONE (PR #588)
37. ~~Use atomic writes for server_pids.txt~~ -- DONE (PR #592)
38. ~~Add module allowlist to dynamic imports~~ -- DONE (PR #585)
39. ~~Replace ipython with python in server bat files~~ -- DONE (PR #578)
40. ~~Switch config loader from JSON to YAML~~ -- DONE (PR #574)
41. ~~Add pytest to environment_staging.yml~~ -- DONE (PR #586)
42. ~~Fix dump_iphone_video crash with multiple acquisition servers~~ -- DONE (PR #580)
43. ~~Handle stale entries in server_pids.txt gracefully~~ -- DONE (PR #607)
44. ~~Parallelize camera start in DeviceManager~~ -- DONE (PR #594)
45. ~~Pre-construct task instances during welcome screen~~ -- DONE (PR #605)
46. ~~Combine StopRecording + StartRecording into TransitionRecording~~ -- DONE (PR #611)
47. ~~Add timing instrumentation to inter-task critical path~~ -- DONE (PR #598)
48. ~~Reduce STM message polling intervals~~ -- DONE (PR #589)
