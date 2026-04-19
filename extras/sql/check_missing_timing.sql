-- check_missing_timing.sql
--
-- Finds log_sensor_file entries where the task completed normally
-- (log_task.task_id is set) but XDF post-processing never populated
-- the timing fields. This means ACQ's early write succeeded but the
-- XDF split either hasn't run yet or failed for this task.
--
-- Rows from today are excluded because post-processing typically
-- runs at end of day. Rows from prior days with NULL timing indicate
-- a post-processing failure that needs investigation.
--
-- Usage:
--   Run the day after a session to verify post-processing completed.
--   Expect 0 rows for dates before today.
--
--   Narrow by date:     Add AND ls.date = '2026-04-18'
--   Narrow by version:  Add AND ls.application_version = 'v0.86.0'

SELECT
    ls.log_session_id,
    ls.date,
    ls.application_version,
    lt.log_task_id,
    lt.task_id,
    lsf.device_id,
    lsf.sensor_file_path
FROM log_sensor_file lsf
JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
JOIN log_session ls ON lt.log_session_id = ls.log_session_id
WHERE lt.task_id IS NOT NULL
  AND lsf.file_start_time IS NULL
  AND ls.date < CURRENT_DATE
ORDER BY ls.date DESC, ls.log_session_id, lt.task_id, lsf.device_id;
