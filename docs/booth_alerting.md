# Booth crash alerting

Status: design + prototype. Not running in any environment yet.

The team should hear about it, with details, when a booth service (CTR, STM, ACQ_n)
logs an error or dies, and should be able to search past failures. PR #860 gets
every kind of failure into the neurobooth database; `neurobooth_os/alerting.py` reads
the database and sends notifications.

## Where it runs

Each environment has its own database, reached from the booths through its own SSH
jump host (from `configs`, `environments/*/neurobooth_os_config.yaml`):

| Environment | Database | DB host | Jump host |
|---|---|---|---|
| wang | `neurobooth` | 192.168.100.1 | neurodoor |
| ctru | `mock_neuroroom` | 192.168.100.1 (a different private network) | ctrudoor |
| merrimac | `FA_study` | neurodoor2 | neurodoor2 |
| staging | `staging` | neurodoor2 | neurodoor2 |

So the alerter runs **on each environment's CTR machine**, as a Task Scheduler entry
that starts `python -m neurobooth_os.alerting run` every minute. It ships with the
release, reads its settings from the environment's config, and connects through
`metadator.get_database_connection()` with the tunnel and credentials the CTR
already has. No server outside the booths needs anything installed.

```
CTR machine (per environment)                       environment's database
  Task Scheduler, every minute                        log_application
    pythonw -m neurobooth_os.alerting run  --tunnel-> service_heartbeat
        |                                             subject (IDs only, to scrub)
        +--> email / Teams                            alert_history, alerter_state
```

It runs as its own process, not inside the GUI, so a CTR process crash is still
reported. A PostgreSQL advisory lock (`pg_try_advisory_xact_lock`) lets only one
alerter work on a database at a time; staging and Merrimac share the CTR machines
under different accounts, and a second copy started by hand just skips its run.

If the alerter itself fails, the failure is logged to `log_application` at ERROR, so
the next successful run alerts on it like any other error.

### Not covered: the CTR machine itself going down

If the CTR machine powers off, loses its network or hangs, its alerter stops too and
nothing is sent. Service crashes on the other machines are still recorded (#860's
heartbeat and crash-log backfill), and are reported once the CTR is back. We are
accepting this gap for now. Ideas for closing it, cheapest first:

1. **Standby alerters on STM and ACQ.** Register the same task on the other booth
   machines of the environment. The advisory lock means only one of them works each
   minute, so whichever machine is up does the job, and it sees the CTR heartbeat go
   stale and reports it. No new infrastructure; it only fails if the whole site is
   down. STM and ACQ machines record and present, so the timing check under
   **Open questions** matters more there.
2. **A daily "all clear".** Each alerter sends one short summary a day (open alerts,
   counts of repeats that were not re-sent). If it doesn't arrive, someone notices.
   It relies on a person noticing something missing, but it costs a few lines.
3. **A dead-man's switch in Microsoft 365.** Each run pings a Power Automate HTTP
   flow that records the time; a scheduled flow posts to Teams if a site hasn't
   pinged for, say, 15 minutes. Stays inside MGB's tenant, but the flows belong to
   whoever created them.
4. **A dead-man's-switch service** (e.g. Healthchecks.io, which can also be
   self-hosted). Each run requests a per-site URL; the service alerts when the
   requests stop. Only a ping leaves the booth, but it is a third-party service and
   would need approval.
5. **Ask MGB IT** whether the booth machines are already covered by endpoint or
   uptime monitoring that could alert this team.

Idea 1 seems the best next step: it reuses everything here and adds only a
scheduled task on two more machines.

## Inputs

All from the environment's database:

- **`log_application`**, rows at `log_level` `error` or `critical`. Two `device` values
  mark rows that #860 backfills at startup, whose own `filename`/`line_no` point at the
  backfill rather than the failure:
  - `crash_log`: a faulthandler trace recovered from `neurobooth_crash_<service>.log`.
  - `db_fallback_log`: a record replayed from the DB-fallback file after an outage.
- **`service_heartbeat`** (`sql/migration/service_heartbeat_v0.96.0.sql`, #860). A row
  with `stopped_at IS NULL` and a stale `last_beat` is a process that stopped without a
  clean shutdown.

## Why not Grafana alerting

| | Grafana alerting (Postgres datasource) | `neurobooth_os.alerting` |
|---|---|---|
| Installed | A Grafana server (its own database and web UI) somewhere that can reach every environment's database, plus SMTP settings and auth | Nothing new; ships with neurobooth-os |
| Dedup by fingerprint, re-alert only after acknowledgement | Not a Grafana concept. Rules fire and resolve per label set, and acknowledging means a silence, which expires. Normalizing messages would have to be done in SQL regexes inside the rule. | Built in (below) |
| Query shape | Alert conditions must be time-series queries (a `time` column plus numeric values) [1] | Any SQL |
| Alert history | In Grafana's own state history | `alert_history` in each environment's database |
| Upkeep | Grafana upgrades and patches on a server we would have to get | Code in this repo with unit tests; changes go through normal PRs |
| What you also get | Dashboards | Nothing beyond alerts |

Grafana could still be added later as a read-only dashboard over `alert_history`
and `service_heartbeat`.

## Fingerprinting and dedup

A fingerprint is the first 16 hex digits of SHA-256 over:

- **kind**: `log` or `dead_service`
- **server_type** (CTR, STM, ACQ_0, ...) and **server_id** (hostname)
- **location**: `filename:line_no`. For `crash_log` rows it is the innermost frame of
  the thread faulthandler marked `Current thread`; for `db_fallback_log` rows it is the
  `file.py:line` inside the replayed record. Dead services use `heartbeat`.
- **normalized message**: subject/session IDs scrubbed, then UUIDs, `0x...` addresses
  and digit runs replaced with placeholders, whitespace collapsed, cut to 300
  characters. For crash traces the message is the first trace line, such as
  `Windows fatal exception: access violation`.

Each run:

1. Takes the advisory lock, or skips the run if another alerter holds it.
2. Reads `log_application` from the stored watermark minus a 60-minute overlap, and
   stale heartbeats (no beat for 5 minutes, last beat within 24 hours).
3. Skips any occurrence no later than its fingerprint's `last_seen`. This is what
   makes the overlap safe: because the fingerprint includes the machine, `last_seen`
   and the new row come from the same clock.
4. **New fingerprint** → alert. **Repeat of an unacknowledged fingerprint** → count
   only. **Repeat of an acknowledged fingerprint** → alert and clear the
   acknowledgement.
5. Sends one notification for all of this run's alerts, then commits. If the send
   fails, the transaction rolls back and the next run retries, so an alert is never
   lost to a mail outage (it can be duplicated if the commit itself fails after a
   successful send).

Watermark: the latest `server_time` read, never past the database's `now()`, so one
booth with a fast clock can't hide rows from the others. A booth clock more than an
hour slow would have rows missed; widen `log_overlap_min` if that turns out to happen.

Known consequences of the fingerprint choice:

- Line numbers move between releases, so after an upgrade a still-present bug alerts
  once more under its new line.
- The same bug on three ACQ machines is three fingerprints, listed in one email.
- Every death of one service on one machine shares a fingerprint, so a second CTR
  crash before anyone acknowledges the first is counted but not re-sent.
- A booth that loses its database tunnel for over 5 minutes stops beating and is
  reported as dead; the message says "crashed, hung, or lost its database connection".

## Alert history table

`sql/migration/booth_alerts_v0.96.0.sql` creates, in each environment's database:

- **`alert_history`**: one row per fingerprint, with `kind`, `server_type`,
  `server_id`, `location`, `normalized_message`, the latest scrubbed
  `sample_message`/`sample_traceback`, `log_level`, `first_seen`, `last_seen`,
  `count`, `acknowledged`, `acknowledged_at`, `acknowledged_by`, `last_notified_at`,
  `notify_count`.
- **`alerter_state`**: a single row with the `log_watermark` and `last_run_at`.

Searching history: `alert_history` for "what has failed and how often", then
`log_application` filtered by `server_id`, `filename`, `line_no` and the time range for
the individual rows, including the session.

Acknowledging, from any machine with the environment's config:

```
python -m neurobooth_os.alerting list
python -m neurobooth_os.alerting ack 3f9c2a --by spencer
```

## Notification channel

Both channels are supported; use whichever the CTR machines can reach.

- **Teams, through a Workflows flow** (`teams_webhook_url`). The booths already reach
  OneDrive, so outbound HTTPS probably works. Office 365 connector webhooks are
  retired; Microsoft set March 31, 2026 as the end of its extended migration period
  [2], and the replacement is a flow in the Teams Workflows app [3]. A flow belongs to
  the person who created it, so it stops if that account goes away.
- **Email through the MGH SMTP relay** (`smtp`), to a team distribution list. The
  booths are not on the VPN, so whether they can reach the relay is unknown.

`python -m neurobooth_os.alerting test-notify` on a CTR settles which works.

### Keeping subject IDs out of notifications

- `session_id` is never read. It holds the session name, `<subject_id>_<date>`.
- `subject_id` is read only to scrub it out of that row's message and traceback.
- Every message and traceback is also scrubbed of session names
  (`<id>_YYYY-MM-DD`, including inside data paths) and of every ID in the `subject`
  table, matched as whole tokens. This runs before anything is stored in
  `alert_history` or sent, and the notification is built only from `alert_history`.
- Not covered: names or other identifiers inside a free-text log message. A search
  of `neurobooth_os/` found no log call that includes subject names, but nothing
  enforces that.

## Setting it up in an environment

Nothing below has been done in any environment yet.

1. Apply `service_heartbeat_v0.96.0.sql` (#860) and `booth_alerts_v0.96.0.sql`.
2. Make sure the database user in the config can read `log_application`,
   `service_heartbeat` and `subject.subject_id`, and read and write `alert_history`
   and `alerter_state`.
3. Add an `alerting` section to the CTR's `neurobooth_os_config.yaml` (model:
   `AlertingSpec` in `neurobooth_os/config.py`), with secrets in `secrets.yaml`:
   ```yaml
   # neurobooth_os_config.yaml
   alerting:
     label: Neurobooth Wang
     smtp:
       host: <relay host>
       sender: neurobooth-alerts@<domain>
       recipients: [<team list>]

   # secrets.yaml
   production:
     alerting:
       teams_webhook_url: "<Workflows flow URL>"
   ```
4. On the CTR, from the environment's account: `python -m neurobooth_os.alerting
   test-notify`, then `extras\register_alerter_task.bat`. The task runs
   `pythonw.exe` (no console window) every minute while that account is logged on.

The first run looks back 24 hours, so expect one notification covering that day.

## Open questions

- Can the CTR machines reach the MGH SMTP relay, a Teams Workflows URL, or both?
- Which distribution list or Teams channel should receive alerts?
- Is there an index on `log_application.server_time`? The alerter filters on it every
  minute through the tunnel; check with `EXPLAIN`.
- Does a one-query-a-minute background task affect recording timing on the CTR?
  It should be negligible, but it should be checked with a timing run, and more
  carefully before trying standby alerters on STM or ACQ.
- Are the CTR accounts logged on whenever the booth is in use? The task only runs
  while they are (`/IT`), which avoids storing a Windows password in Task Scheduler.

## Verification status

- Unit tests (`tests/pytest/test_alerting.py`) cover scrubbing, normalization,
  fingerprints for all three row types, the dedup rules, the lock, notification
  content, settings, and `run_once` against an in-memory store.
- **Not yet verified:** the SQL in `PostgresAlertStore` has not run against
  PostgreSQL; no email or Teams message has been sent; the Task Scheduler entry has
  not been registered on a booth.

## Sources

1. Grafana docs, "PostgreSQL alerting":
   <https://grafana.com/docs/grafana/latest/datasources/postgres/alerting/>
2. Microsoft 365 Developer Blog, "Retirement of Office 365 connectors within Microsoft
   Teams" (updated October 2025):
   <https://devblogs.microsoft.com/microsoft365dev/retirement-of-office-365-connectors-within-microsoft-teams/>
3. Microsoft 365 Message Center MC808160:
   <https://mc.merill.net/message/MC808160>
