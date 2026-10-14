# Booth crash alerting

Status: design + prototype. Nothing is installed on neurodoor yet.

The team should hear about it, with details, when a booth service (CTR, STM, ACQ_n)
logs an error or dies, and should be able to search past failures. PR #860 gets
every kind of failure into the neurobooth database; this layer reads the database
and sends notifications.

```
booths --(SSH tunnel)--> PostgreSQL on neurodoor <-- booth_alerter.py (cron, every minute)
                         log_application                 |
                         service_heartbeat               +--> alert_history / alerter_state
                         subject (IDs only, to scrub)    +--> email (MGH SMTP relay)
                                                         +--> Teams (optional)
```

## Inputs

All from the neurobooth database:

- **`log_application`**, rows at `log_level` `error` or `critical`. Two `device` values
  mark rows that #860 backfills at startup, whose own `filename`/`line_no` point at the
  backfill rather than the failure:
  - `crash_log`: a faulthandler trace recovered from `neurobooth_crash_<service>.log`.
  - `db_fallback_log`: a record replayed from the DB-fallback file after an outage.
- **`service_heartbeat`** (`sql/migration/service_heartbeat_v0.96.0.sql`, #860). A row
  with `stopped_at IS NULL` and a stale `last_beat` is a process that stopped without a
  clean shutdown.

## Grafana alerting vs. a small Python alerter

| | Grafana alerting (Postgres datasource) | `extras/booth_alerter.py` (cron) |
|---|---|---|
| Installed on neurodoor | Grafana server (a service with its own database, web UI on port 3000), SMTP settings in `grafana.ini`, a Postgres datasource, auth for anyone who opens the UI | Python 3.8+ and psycopg2, one config file, one cron line |
| Dedup by fingerprint, re-alert only after acknowledgement | Not a Grafana concept. Rules fire and resolve per label set, and acknowledging means a silence, which expires. Normalizing messages would have to be done in SQL regexes inside the rule. | Built in (below) |
| Query shape | Alert conditions must be time-series queries (a `time` column plus numeric values) [1] | Any SQL |
| Alert history | In Grafana's own state history, not in the neurobooth database | `alert_history` table in the neurobooth database, queryable with SQL |
| Upkeep | Grafana upgrades and security patches; rules and contact points provisioned as YAML or kept in the UI | ~900 lines in this repo with unit tests; changes go through normal PRs |
| What you also get | Dashboards | Nothing beyond alerts |

**Recommendation: the Python alerter.** The requirement that sets this apart is
"alert on a new fingerprint, or on a recurrence after it was acknowledged", which is
a few lines of Python and awkward to express in Grafana. It also installs almost
nothing on a server whose permissions and outbound access are not yet confirmed.
If dashboards are wanted later, Grafana can be added as a read-only viewer over
`alert_history` and `service_heartbeat` without moving the alerting.

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

1. Reads `log_application` from the stored watermark minus a 60-minute overlap, and
   stale heartbeats (no beat for 5 minutes, last beat within 24 hours).
2. Skips any occurrence no later than its fingerprint's `last_seen`. This is what
   makes the overlap safe: because the fingerprint includes the machine, `last_seen`
   and the new row come from the same clock.
3. **New fingerprint** → alert. **Repeat of an unacknowledged fingerprint** → count
   only. **Repeat of an acknowledged fingerprint** → alert and clear the
   acknowledgement.
4. Sends one notification for all of this run's alerts, then commits. If the send
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

`sql/migration/booth_alerts_v0.96.0.sql` creates:

- **`alert_history`**: one row per fingerprint, with `kind`, `server_type`,
  `server_id`, `location`, `normalized_message`, the latest scrubbed
  `sample_message`/`sample_traceback`, `log_level`, `first_seen`, `last_seen`,
  `count`, `acknowledged`, `acknowledged_at`, `acknowledged_by`, `last_notified_at`,
  `notify_count`.
- **`alerter_state`**: a single row with the `log_watermark` and `last_run_at`.

Searching history: `alert_history` for "what has failed and how often", then
`log_application` filtered by `server_id`, `filename`, `line_no` and the time range for
the individual rows, including the session.

Acknowledging:

```
python booth_alerter.py --config booth_alerter.json list
python booth_alerter.py --config booth_alerter.json ack 3f9c2a --by spencer
```

## Notification channel

**Email through the MGH SMTP relay**, sent to a team distribution list.

- Office 365 connector webhooks in Teams are retired; Microsoft set March 31, 2026
  as the end of its extended migration period [2], and the replacement is a flow in
  the Teams Workflows app [3]. A Workflows flow belongs to the person who created it,
  so it stops if that account goes away; a distribution list does not.
- Email stays inside the MGB mail system, which matters even with scrubbing in place.

The alerter can also post to a Teams Workflows URL (`teams_webhook_url`) as a second
channel. That payload has not been tried against a real flow.

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

## Running it on neurodoor

Nothing below has been done; it needs Spencer's go-ahead and the answers under
**Open questions**.

1. Apply `service_heartbeat_v0.96.0.sql` (#860) and `booth_alerts_v0.96.0.sql`.
2. Create a role with only what the alerter needs:
   ```sql
   CREATE ROLE neurobooth_alerter LOGIN;
   GRANT SELECT ON log_application, service_heartbeat TO neurobooth_alerter;
   GRANT SELECT (subject_id) ON subject TO neurobooth_alerter;
   GRANT SELECT, INSERT, UPDATE ON alert_history, alerter_state TO neurobooth_alerter;
   ```
3. Copy `extras/booth_alerter.py` and a filled-in `booth_alerter.json` (from
   `booth_alerter.example.json`, mode 600; leave `password` null to use `~/.pgpass`).
4. `python booth_alerter.py --config booth_alerter.json test-notify`
5. Cron, with `flock` so a slow run can't overlap the next and `MAILTO` so a failing
   alerter is itself reported:
   ```
   MAILTO=neurobooth-team@...
   * * * * * flock -n /tmp/booth_alerter.lock python3 /path/booth_alerter.py --config /path/booth_alerter.json run
   ```

The first run looks back 24 hours, so expect one notification covering that day.

## Open questions

- Can neurodoor reach the MGH SMTP relay, and which host/port? Does it relay without
  authentication from that host?
- Does Spencer's account on neurodoor allow cron jobs and `pip install --user` (or a
  venv)? Which Python version is there?
- Is PostgreSQL on neurodoor itself, or reached from it?
- Which distribution list should receive alerts?
- Is there an index on `log_application.server_time`? The alerter's query filters on
  it every minute; check with `EXPLAIN` before scheduling.

## Verification status

- Unit tests (`tests/pytest/test_booth_alerter.py`) cover scrubbing, normalization,
  fingerprints for all three row types, the dedup rules, notification content, and
  `run_once` against an in-memory store.
- **Not yet verified:** the SQL in `PostgresAlertStore` has not run against
  PostgreSQL; no email or Teams message has been sent.

## Sources

1. Grafana docs, "PostgreSQL alerting":
   <https://grafana.com/docs/grafana/latest/datasources/postgres/alerting/>
2. Microsoft 365 Developer Blog, "Retirement of Office 365 connectors within Microsoft
   Teams" (updated October 2025):
   <https://devblogs.microsoft.com/microsoft365dev/retirement-of-office-365-connectors-within-microsoft-teams/>
3. Microsoft 365 Message Center MC808160:
   <https://mc.merill.net/message/MC808160>
