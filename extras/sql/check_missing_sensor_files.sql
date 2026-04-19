-- check_missing_sensor_files.sql
--
-- Finds completed tasks that have NO log_sensor_file entries at all.
-- This means both ACQ's early write and XDF post-processing failed
-- (or never ran) for a task that should have recorded data.
--
-- Excludes non-recording task types (pause, progress bar, break,
-- intro, coord_pause) which are not expected to produce sensor files.
--
-- Usage:
--   Run after post-processing to catch tasks where all registration
--   paths failed. Expect 0 rows on a healthy session.
--
--   Narrow by date:     Add AND ls.date >= '2026-04-17'
--   Narrow by session:  Add AND ls.log_session_id = 3190

SELECT
    ls.log_session_id,
    ls.date,
    ls.application_version,
    lt.log_task_id,
    lt.task_id
FROM log_task lt
JOIN log_session ls ON lt.log_session_id = ls.log_session_id
LEFT JOIN log_sensor_file lsf ON lsf.log_task_id = lt.log_task_id
WHERE lt.task_id IS NOT NULL
  AND lsf.log_sensor_file_id IS NULL
  AND lt.task_id NOT LIKE 'pause_%'
  AND lt.task_id NOT LIKE 'progress_%'
  AND lt.task_id NOT LIKE 'break_%'
  AND lt.task_id NOT LIKE 'intro_%'
  AND lt.task_id NOT LIKE 'coord_pause_%'
ORDER BY ls.date DESC, ls.log_session_id, lt.task_id;
