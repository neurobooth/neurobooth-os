# Windows 11 `.bat` audit

Static audit of the booth deploy chain's `.bat` files for Windows 11 compatibility. Scopes concern #7 of #759 and is the deliverable of #766.

Empirical verification (actually launching each script on a Win11 booth) is operator work scheduled for Phase 3 (#769) — this doc captures the static read so the pilot has a checklist to diff against.

## Inventory drift from issue body

Three of the scripts named in #766's table no longer match what's on master:

- **`neurobooth_os/install.bat`** — removed in [#780](https://github.com/neurobooth/neurobooth-os/pull/780) (v0.92.2). Concerns #766 risk-#2 (winget package ID stability) and risk-#4 (PowerShell version) lived entirely in this file and are now **moot**.
- **`extras/serv_acq_upload - neurobooth_OS.bat`** — removed in [#793](https://github.com/neurobooth/neurobooth-os/pull/793) (v0.92.2). Concern #766 risk-#6 (spaces in filename) is **moot**.
- **`github_checkout.bat`** (repo root) — added since the issue was authored. New bat file under audit (rows below).

## Per-script audit

All paths relative to repo root. Severity: **none** (no Win11-specific risk), **low** (works but worth eyeballing on first pilot run), **carryover** (Win10-fragile pattern that Win11 inherits but does not amplify).

| Script | Lines | Win11-specific risk | Notes |
|---|---|---|---|
| `neurobooth_os/server_acq.bat` | 2 | none | `call activate.bat` + `start /W python server_acq.py %1`. The Python child is a non-interactive daemon (LSL/sockets), so ConPTY/ANSI behaviour under Windows Terminal does not apply. |
| `neurobooth_os/server_stm.bat` | 2 | none | Same shape as `server_acq.bat`. |
| `neurobooth_os/server_ctr.bat` | 2 | none | Same shape, launches `gui.py` (PySimpleGUI window). `start /W` on a windowed GUI app behaves identically on Win10 / Win11. |
| `neurobooth_os/transfer_data.bat` | 3 | none | Two sequential `start /W python` calls (dump + transfer). Already migrated off `ipython` in [#784](https://github.com/neurobooth/neurobooth-os/pull/784), so the issue's risk-#1 (ConPTY interaction with `ipython --pdb`) does not apply. |
| `extras/add_subject.bat` | 2 | none | Plain `start /W python`. No interactive TUI (also migrated off `ipython`). |
| `extras/camera.bat` | 2 | none | Cosmetic: `call start /W python ...` chains `call` ahead of `start /W` redundantly, but works on both OSes. |
| `extras/reset_mbients.bat` | 3 | none | Reads `%USERPROFILE%\mbients.json`. `pause` at end works on both. |
| `extras/postprocess_split_xdf.bat` | 2 | none | Same redundant `call start /W` pattern as `camera.bat`. |
| `extras/iphone_stress_test.bat` | 361 | **carryover** | Hardcodes `SET DATA_OUT="D:\iphone_stress_test"` on line 10 and `CD "%NB_INSTALL%\neurobooth_os\iout"`. Already fragile on Win10 (assumes a D: drive exists and is writable). Win11 inherits the fragility unchanged. Not Win11-blocking; a small env-var-driven rewrite would be a Win10-and-Win11 improvement but is out of scope for this audit. |
| `github_checkout.bat` | 65 | none | Uses `setlocal enabledelayedexpansion`, `%~nx0`, `%~1`, heredoc-style `( ... ) > file`, `git rev-parse / fetch / checkout`. All standard primitives, both OSes. Writes `neurobooth_os/current_release.py` at git-checkout time; this is intentional and separate from `configs/version.bat`'s `current_config.py` stamping at deploy time (see `pyproject.toml:26-28`). |

`tests/deployment-test/run_timing_tests.bat` and `run_timing_tests_plotting.bat` are intentionally excluded — they are covered structurally by #761 and will be rewritten as part of the timing-harness rebuild.

## Cross-cutting findings against the issue's risk list

| # | Risk from #766 body | Status |
|---|---|---|
| 1 | ConPTY / Windows Terminal default host changes `start /W` interaction with `ipython --pdb` TUIs | **Moot** — all `ipython` invocations were removed in #784 / #793. No script in scope launches an interactive TUI. |
| 2 | `winget` package IDs may have moved on Win11 | **Moot** — `install.bat` (the only winget-using script) was removed in #780. |
| 3 | `%NB_INSTALL%` env var setup procedure differs on Win11 Settings UI | **Low** — env var semantics unchanged; only the Settings screenshot path differs. Affects setup docs, not script behaviour. README may need a Win11 screenshot. |
| 4 | PowerShell version assumptions in install one-liners | **Moot** — only `install.bat` had PowerShell calls (in comments); script removed. |
| 5 | Leaked `wmic` / `netsh` / `SCHTASKS` / `tasklist` outside `netcomm/client.py` | **Clear** — verified zero matches across all `.bat` files (`Grep` on `(?i)\b(wmic\|netsh\|schtasks\|tasklist)\b` returned no hits). |
| 6 | Script with literal spaces in filename | **Moot** — removed in #793. |
| 7 | `DEL /Q /S` / `MKDIR` against fixed paths in `iphone_stress_test.bat` | **Carryover** — `D:\iphone_stress_test` hardcoded; Win10-fragile already, Win11 inherits unchanged. Not Win11-blocking. |
| 8 | `%~dp0\..` path resolution edges | **N/A** — no current script uses `%~dp0`. All resolve paths via `%NB_INSTALL%`. The UNC-launched-bat-file edge case does not apply. |

## Configs-repo scripts (operator-doable, not in this audit)

`configs/checkout_and_deploy.bat` and `configs/version.bat` live in the separate `neurobooth/configs` repo and were not read here. Per [#758](https://github.com/neurobooth/neurobooth-os/pull/758) they should now be uv-based (no conda residue). Operator should:

1. Walk both scripts on a Win11 pilot booth.
2. Confirm `configs/version.bat`'s `current_config.py` stamping still works on Win11 (PowerShell or `>` redirection, depending on how `version.bat` writes the file).
3. Confirm the README's `## Setup` flow works end-to-end on a fresh Win11 install (in-place env-var setup + clone + deploy).

This audit cannot complete that coverage from inside `neurobooth-os`.

## Verdict

**No code follow-ups required from this audit.** The Win11 risk surface for in-repo `.bat` files is dominated by primitives unchanged from Win10 (`call`, `start /W`, `setlocal`, `%VAR%` expansion, `SET`, `MKDIR`, `DEL /Q /S`, `git`). The three highest-risk scripts the issue named (`install.bat`, the spaces-in-filename upload script, anything using `ipython`) were already removed or rewritten in #780 / #784 / #793 before this audit ran.

Open items, ordered by what they affect:

- **Phase 3 (#769) operator action**: actually launch each in-scope `.bat` on the Win11 pilot booth and confirm exit codes match the Win10 baseline. The per-script rows above are the checklist.
- **Phase 3 (#769) cross-repo action**: walk `configs/checkout_and_deploy.bat` and `configs/version.bat` on the Win11 pilot booth per the section above.
- **Optional Win10-and-Win11 cleanup**: `iphone_stress_test.bat`'s `D:\iphone_stress_test` should read from an env var (e.g. `%NB_STRESS_DATA%` with a default). Not gating; not Win11-specific.
- **Doc refresh, not audit-blocking**: `docs/code_audit.md:469` describes `github_checkout.bat` as "just calls `git checkout <tag>`", but the current script also writes `current_release.py`. Either the audit doc is stale or the bat was rewritten after that review. Worth noting next time `code_audit.md` is refreshed.

## Anomaly: optional cleanup (out of Win11 scope)

`extras/iphone_stress_test.bat`'s 99 `python iphone.py ...` calls (one per task per session × 10 sessions) all share identical arg shapes apart from `--duration` and `--subject-id`. The script is ~360 lines of near-duplication. A Python or PowerShell driver reading a small CSV/JSON table of `(session_id, percentile, task, duration)` would shrink this to a couple of dozen lines while losing nothing. Independent of the OS upgrade; flag only because the audit had to read every line.

## References

- #766 — this issue
- #759 — Win11 upgrade umbrella, concern #7
- #761, #769, #758 — referenced above
- `pyproject.toml:26-28` — settles the `current_release.py` vs `current_config.py` two-file design
