-- check_orphan_sensor_files.sql
--
-- Finds log_sensor_file entries from tasks that never completed
-- (cancelled or crashed before _perform_task finished). These are
-- identified by log_task.task_id being NULL — the log_task row was
-- pre-created at TransitionRecording time but never filled in.
--
-- Background:
--   Starting with v0.86.0, ACQ writes log_sensor_file rows at device
--   start time so that files are always tracked in the database. If
--   the session is then cancelled or STM crashes, those rows remain
--   with NULL timing fields and their parent log_task has task_id NULL.
--   The neurobooth-terra copy script (with the companion filter from
--   neurobooth/neurobooth-terra#75) skips these files during transfer.
--
-- Usage:
--   Run to audit orphan entries. Expect rows only for sessions where
--   a cancel or crash occurred. Healthy sessions should have 0 rows.
--
--   Filter by date:     WHERE ls.date >= '2026-04-17'
--   Filter by session:  WHERE ls.log_session_id = 3190
--   Filter by version:  WHERE ls.application_version = 'v0.86.0'

-- Orphan sensor file entries (task never completed)
SELECT
    ls.log_session_id,
    ls.date,
    ls.application_version,
    lt.log_task_id,
    lt.task_id,
    lsf.device_id,
    lsf.sensor_file_path,
    lsf.file_start_time
FROM log_sensor_file lsf
JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
JOIN log_session ls ON lt.log_session_id = ls.log_session_id
WHERE lt.task_id IS NULL
  -- Uncomment one of these filters:
  -- AND ls.date >= '2026-04-17'
    AND ls.application_version = 'v0.86.0'
ORDER BY ls.date DESC, ls.log_session_id, lsf.device_id;

-- Summary: count of orphan entries per session
-- SELECT
--     ls.log_session_id,
--     ls.date,
--     COUNT(*) AS orphan_count
-- FROM log_sensor_file lsf
-- JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
-- JOIN log_session ls ON lt.log_session_id = ls.log_session_id
-- WHERE lt.task_id IS NULL
-- GROUP BY ls.log_session_id, ls.date
-- ORDER BY ls.date DESC;

-- Cleanup: delete orphan entries older than 30 days
-- (Only run after confirming the data is not needed)
-- DELETE FROM log_sensor_file
-- WHERE log_task_id IN (
--     SELECT lt.log_task_id
--     FROM log_task lt
--     JOIN log_session ls ON lt.log_session_id = ls.log_session_id
--     WHERE lt.task_id IS NULL
--       AND ls.date < CURRENT_DATE - INTERVAL '30 days'
-- );
