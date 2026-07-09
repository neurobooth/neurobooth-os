# Real-device data-collection test (dod_laptop / issue #713)

A quick, repeatable way to confirm the real devices (EyeLink, mic, iPhone,
mouse) actually **captured data** in a session — not just that the GUI ran.

Run everything below with the project venv python
(`.venv\Scripts\python`) from the neurobooth-os checkout.

## A. Pre-session readiness (before you start the session)

- [ ] **Active config = dod_laptop, mocks off**
  ```
  python -c "from neurobooth_os import config; config.load_config(validate_paths=False); c=config.neurobooth_config; print(c.environment, c.mock_devices, c.database.dbname)"
  ```
  Expect: `dod_laptop None dod_neurobooth`
- [ ] **EyeLink Host PC reachable**: `ping 100.1.1.1` (laptop is 100.1.1.2 on the USB-GbE adapter)
- [ ] **iPhone service up**: `Get-Service "Apple Mobile Device Service"` = Running, and
  `Get-NetTCPConnection -State Listen -LocalPort 27015` shows a listener
- [ ] **iPhone itself**: unlocked, neurobooth app in the **foreground**,
  **Settings → Display & Brightness → Auto-Lock = Never**, plugged in / charging,
  "Trust This Computer" accepted. *(This is what prevents the mid-session
  "connection lost: socket closed" panic — see below.)*
- [ ] **Mic**: built-in "Microphone Array" is the default Windows input
- [ ] **DB**: Postgres running, `dod_neurobooth` reachable

## B. Run a short test session

- Use a **small task set** (e.g. `intro_sess` + one gaze task like `pursuit`)
  rather than the full battery — enough to exercise each device, fast to inspect.
- Watch the GUI for any device **PANIC / critical** banner and note the time.

## C. Post-session validation

- [ ] **Data report** (defaults to the newest session folder):
  ```
  python extras/perf/check_session_data.py --db
  # or a specific one:
  python extras/perf/check_session_data.py 100001_2026-07-08 --db
  ```
- [ ] Confirm per device:
  - **EyeLink** — thousands of `Gaze` samples at ~1000 Hz; a non-trivial `.edf` per task
  - **Mic (Audio)** — samples at ~43 Hz across tasks
  - **iPhone** — real `IPhoneFrameIndex` samples (**not** 1 / INIT-ONLY) **and** a `.mov` per task
  - **Mouse / Marker** — present
- [ ] Bottom line reads `RESULT: PASS`
- [ ] *(Registration, optional)* after `split_xdf.py` runs, use
  `validate_session_files.py` to confirm every file has a `log_sensor_file` row.

## What "good" vs "bad" looks like

- **Good capture** = many samples at the device's nominal rate over the task duration.
- **INIT-ONLY** (exactly 1 sample, 0 Hz) = the device registered its stream but never
  streamed data — e.g. the iPhone after a disconnect. No `.mov` = no iPhone video captured.
- A stream **absent** entirely = the device never came up (check the GUI / `log_application`).

## Related tooling
- `check_session_data.py` — this data-content report (per-stream samples).
- `validate_session_files.py` — file→`log_sensor_file` registration audit (production NAS + tunnel).
