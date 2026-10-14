-- Modifications to neurobooth database schema associated with system enhancements

-- These changes can be run at any time BEFORE the associated code changes are applied
-- as it doesn't break anything if it's used for any earlier version and
-- it doesn't break anything if it runs more than once. If those commitments don't hold
-- for some future changes, a separate script will be provided.

-- Each change is commented with the version it is required for

-- The changes are applied in the order required.

-- required for version v0.96.0 and later:
--   Each CTR / STM / ACQ_n process upserts one row per launch every ~30 s
--   (neurobooth_os/service_monitor.py). A row with stopped_at NULL and a stale
--   last_beat is a process that died without shutting down -- a hard crash
--   that never reached log_application. Without this table the service still
--   runs; its heartbeat writes fail and are logged once as a warning.
CREATE TABLE IF NOT EXISTS public.service_heartbeat
(
    service_id      character varying        NOT NULL,  -- CTR, STM, ACQ_0, ...
    server_id       character varying        NOT NULL,  -- machine hostname
    pid             integer                  NOT NULL,
    process_start   timestamp with time zone NOT NULL,
    last_beat       timestamp with time zone NOT NULL DEFAULT now(),  -- DB server time
    stopped_at      timestamp with time zone,           -- set on a clean shutdown
    exit_code       integer,                            -- set on a clean shutdown
    session_id      character varying,                  -- session in progress at the last beat
    release_version character varying,
    PRIMARY KEY (server_id, pid, process_start)
);

-- Finds processes that stopped beating without a clean shutdown.
CREATE INDEX IF NOT EXISTS service_heartbeat_running_idx
    ON public.service_heartbeat (last_beat)
    WHERE stopped_at IS NULL;
