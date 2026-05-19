# Windows 11 Vendor SDK Compatibility

Per-vendor compatibility runbook + the SDK-validation tool inventory called
for by issue #763 (concern #5 of #759). It answers: *which* SDK/driver/
firmware build is on each booth, whether the vendor `.sys`/`.dll` files are
still signed on Win11, and what an operator must install (and in what order)
to bring a Win11 booth up.

Source of truth is the per-run JSON under
[`extras/perf/baselines/sdk/`](../extras/perf/baselines/sdk/) and the booth
log dir; this doc is the human runbook. If the doc and a JSON disagree, the
JSON wins (same convention as `timing_summary.md` / `mbient_soak_summary.md`).

## The tools

| Tool | Produces | Notes |
|---|---|---|
| [`extras/perf/sdk_inventory.py`](../extras/perf/sdk_inventory.py) | `<log_dir>/sdk_inventory/<os>/<host>.json` — SDK/driver/firmware versions for FLIR, RealSense, iPhone, webcam + GPU/USB-controller/audio | Build-first; **fails loudly** if a vendor SDK is absent (never mock-falls-back) |
| `flir_smoke.py` / `realsense_smoke.py` / `iphone_smoke.py` / `webcam_smoke.py` | `<log_dir>/<dev>_smoke/<os>/<host>.json` — version + smallest end-to-end action (one frame / connect+handshake / one DSHOW grab + backend name) | iPhone smoke is connect+handshake **only** (no recording → no video to permanent storage) |
| [`extras/perf/driver_signing_check.py`](../extras/perf/driver_signing_check.py) | `<log_dir>/driver_signing/<os>/<host>.json` — `Get-AuthenticodeSignature` over vendor `.sys`/`.dll` | Pass `--path` with the booth's real vendor dirs (below) |
| [`extras/perf/check_usb_topology.py`](../extras/perf/check_usb_topology.py) `--json` | `<log_dir>/usb_topology/<os>/<host>.json` | The human tree print is unchanged; `--json` is additive |
| [`extras/perf/sdk_compare.py`](../extras/perf/sdk_compare.py) | delta between a locked Win10 artefact and a Win11 one | Flags any SDK/driver/firmware **version roll** or status regression; flag = review, not fail |

`<log_dir>` is the neurobooth `local_log_dir` (`NB_INSTALL` → home fallback).
Runtime artefacts stay out of the repo; a locked baseline is a deliberate
copy into `extras/perf/baselines/sdk/` and commit. Win10-baseline execution
across all four Win11-evaluation harnesses is coordinated under **#768**.

## Per-vendor compatibility runbook

Values marked **(operator to confirm)** require a real booth / the vendor's
site and are intentionally not guessed here (Truth Protocol). The pinned
versions below are from `pyproject.toml` / the guarded imports — facts in the
repo.

| Vendor / SDK | In-repo facts | Min SDK known-good on Win11 | Installer source | Install-order / in-place-upgrade quirks |
|---|---|---|---|---|
| **FLIR / Spinnaker (`PySpin`)** — ACQ | guard `flir_cam.py:_require_pyspin`; `KMP_DUPLICATE_LIB_OK=TRUE` set at `flir_cam.py:46` | (operator to confirm vs Teledyne Win11 matrix) | (operator: Teledyne/FLIR Spinnaker SDK + the matching `spinnaker_python` cp38 wheel) | Spinnaker runtime must be installed before the Python wheel; re-eval the `KMP_DUPLICATE_LIB_OK` workaround on Win11 (below) |
| **Intel RealSense (`pyrealsense2`)** — ACQ | guard `camera_intel.py:_require_pyrealsense2`; pinned `pyrealsense2>=2.54.2.5684` | (operator to confirm; librealsense Win11 support is current) | (operator: Intel RealSense SDK 2.0) | USB-bandwidth scheduling differs on Win11 — check `usb_topology` + `realsense_smoke` one-frame |
| **EyeLink (`pylink`)** — STM | guard `eyelink_tracker.py:_require_pylink` | **deferred — see #807** | SR-Research Developers Kit v2.1.1 (vendor lags new Windows) | EyeLink smoke is a booth-attached follow-up (**#807**): `pylink` is proprietary and unverifiable off-booth |
| **iPhone (usbmux)** — STM | `iphone.py` + `usbmux.py`; #669 `select.select()` race at `usbmux.py:~246` | n/a (no vendor Python SDK) | Apple Mobile Device Support (with iTunes/Apple Devices) | `iphone_smoke` exercises connect/handshake to catch #669 recurrence; **does not record** (no video) |
| **Apple Mobile Device driver** | n/a | (operator to confirm) | bundled with Apple Devices / iTunes | Win11 driver-signing — see `driver_signing_check.py` |
| **Webcam (DirectShow)** — `cv2.CAP_DSHOW` | `webcam.py:113` | OpenCV in the venv (`cv2.__version__`) | n/a (OS) | `webcam_smoke` reports `cap.getBackendName()` so a Win11 DSHOW→MediaFoundation shim fallback is visible |

Suggested `driver_signing_check.py --path` roots (confirm per booth):
`C:\Program Files\Teledyne\Spinnaker`, `C:\Program Files (x86)\Intel RealSense SDK 2.0`,
`C:\Program Files (x86)\SR Research`, `C:\Program Files\Common Files\Apple\Mobile Device Support`.

## Dependency audit (#763 step 6) — what was done and the caveat

**Verified:** zero direct imports of `serial` (pyserial), `parallel`
(pyparallel), or `pywinhook` anywhere in `neurobooth_os/` or `extras/`
(grepped). **Action taken:** the three direct pins were removed from
`pyproject.toml`.

**Honest caveat (read this):** removing the *direct* pins did **not** remove
the packages. After `uv lock`, all three remain in `uv.lock` as
**transitive** dependencies (PsychoPy still requires them). So this is a
*de-duplication of redundant direct declarations*, not a true removal —
nothing was uninstalled and the full test suite still passes. PsychoPy
imports `serial`/`parallel` internally for parallel-port trigger boxes;
whether a booth actually has parallel-port trigger hardware is an operator
fact, not a code fact. If a booth does, that path still works because the
package is still present transitively.

## `KMP_DUPLICATE_LIB_OK` re-evaluation (#763 step 7)

`flir_cam.py:46` sets `KMP_DUPLICATE_LIB_OK=TRUE`, which suppresses an Intel
OpenMP/MKL load-order collision diagnostic. Win11's loader resolves
`libiomp5md.dll` differently (KnownDLLs / SxS shifts), so the collision may
appear or vanish. This **cannot be resolved off-booth** — it must be
*measured* on Win11: run `flir_smoke.py` on a Win11 booth (importing
`flir_cam` applies the flag) and, separately, an operator should test FLIR
acquisition with the line temporarily removed to see whether the underlying
conflict still occurs. If it no longer does on Win11, the suppression can be
dropped. Tracked as the open item of this doc, not silently closed.

## Win10 baseline → Win11 comparison

_Not yet captured — operator work under #768. No numbers here until the
JSONs are committed._

| Booth | inventory | signing | usb_topology | smoke (flir/rs/iphone/webcam) | Date |
|---|---|---|---|---|---|
| ACQ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |
| STM | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |

## Out of scope (per #763)

- Replacing any vendor SDK (PySpin/pylink/pyrealsense2).
- DSHOW → MediaFoundation migration (tracked separately if `webcam_smoke`
  surfaces a Win11 issue).
- Fixing #669 (iPhone usbmux race) — the smoke only *exercises* it to catch
  recurrence.
- EyeLink smoke — deferred to **#807** (proprietary SDK, booth-only).

## References

- Sibling harnesses: `timing_summary.md` (#761), `mbient_soak_summary.md` (#762)
- Issues: #759 (umbrella, concern #5), #763 (this), #807 (EyeLink follow-up),
  #768 (Win10 baseline lockdown), #669 (iPhone usbmux race)
