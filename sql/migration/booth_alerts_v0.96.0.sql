-- Modifications to neurobooth database schema associated with system enhancements

-- These changes can be run at any time BEFORE the associated code changes are applied
-- as it doesn't break anything if it's used for any earlier version and
-- it doesn't break anything if it runs more than once. If those commitments don't hold
-- for some future changes, a separate script will be provided.

-- Each change is commented with the version it is required for

-- The changes are applied in the order required.

-- required for the booth alerter (extras/booth_alerter.py, docs/booth_alerting.md),
-- which runs on neurodoor and reads log_application and service_heartbeat
-- (service_heartbeat_v0.96.0.sql). No booth service reads or writes these tables.

--   One row per distinct failure. A fingerprint is a hash of the service, machine,
--   source location and normalized message, so repeats of the same error share a row.
--   Text columns hold scrubbed samples only: no subject or session IDs.
CREATE TABLE IF NOT EXISTS public.alert_history
(
    fingerprint        character varying        NOT NULL PRIMARY KEY,
    kind               character varying        NOT NULL,  -- 'log' or 'dead_service'
    server_type        character varying        NOT NULL,  -- CTR, STM, ACQ_0, ...
    server_id          character varying        NOT NULL,  -- machine hostname
    location           character varying        NOT NULL,  -- file.py:line, or 'heartbeat'
    normalized_message text                     NOT NULL,
    sample_message     text,                               -- scrubbed, latest occurrence
    sample_traceback   text,                               -- scrubbed, latest occurrence
    log_level          character varying,
    first_seen         timestamp with time zone NOT NULL,
    last_seen          timestamp with time zone NOT NULL,
    count              integer                  NOT NULL DEFAULT 1,
    acknowledged       boolean                  NOT NULL DEFAULT false,
    acknowledged_at    timestamp with time zone,
    acknowledged_by    character varying,
    last_notified_at   timestamp with time zone,
    notify_count       integer                  NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS alert_history_last_seen_idx
    ON public.alert_history (last_seen);

--   Single row: how far through log_application the alerter has read.
CREATE TABLE IF NOT EXISTS public.alerter_state
(
    singleton     boolean                  NOT NULL PRIMARY KEY DEFAULT true CHECK (singleton),
    log_watermark timestamp with time zone,
    last_run_at   timestamp with time zone
);
