-- check_missing_video_files.sql
--
-- Finds log_sensor_file entries where a camera device recorded but its
-- video file (.avi, .bag, .mov) is missing from the sensor_file_path array.
--
-- Background:
--   Each camera device (FLIR, Intel, iPhone) produces both an LSL data
--   stream (saved as .hdf5 via XDF split) and a video file (.avi/.bag/.mov).
--   The split_sens_files() function writes both paths into sensor_file_path.
--   If the video file path is missing, downstream scripts that look up
--   files by extension will report "log_sensor_file_id not found".
--
-- Root cause (fixed in v0.81.0):
--   A race condition between the message reader thread and the GUI thread
--   allowed RecordingFiles for the next task (sent via TransitionRecording)
--   to be buffered before stop_lsl_recording snapshotted task_video_files,
--   causing the current task to capture both tasks' files and the next
--   task to get none. See GitHub issue #659.
--
-- Usage:
--   Run after deploying a new version to verify that video files are
--   being registered correctly. Expect 0 rows on a healthy session.
--
--   Filter by version:  WHERE ls.application_version = 'v0.81.0'
--   Filter by date:     WHERE ls.date >= '2026-04-10'
--   Filter by session:  WHERE ls.log_session_id = 3180

SELECT
    ls.log_session_id,
    ls.date,
    ls.application_version,
    lt.task_id,
    lsf.device_id,
    lsf.sensor_file_path
FROM log_sensor_file lsf
JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
JOIN log_session ls ON lt.log_session_id = ls.log_session_id
WHERE lsf.device_id IN ('FLIR_blackfly_1', 'Intel_D455_1', 'Intel_D455_2',
                         'Intel_D455_3', 'IPhone_dev_1', 'Eyelink_1'
                         -- , 'Webcam_dev_1'  -- uncomment if webcam is deployed
                         )
  AND NOT (
      -- FLIR produces .avi
      (lsf.device_id = 'FLIR_blackfly_1' AND lsf.sensor_file_path::text LIKE '%_flir.avi%')
      -- Intel cameras produce .bag
      OR (lsf.device_id LIKE 'Intel_D455_%' AND lsf.sensor_file_path::text LIKE '%_intel%.bag%')
      -- iPhone produces .mov and .json
      OR (lsf.device_id = 'IPhone_dev_1'
          AND lsf.sensor_file_path::text LIKE '%_IPhone.mov%'
          AND lsf.sensor_file_path::text LIKE '%_IPhone.json%')
      -- EyeLink produces .edf
      OR (lsf.device_id = 'Eyelink_1' AND lsf.sensor_file_path::text LIKE '%.edf%')
      -- Webcam produces .avi (uncomment if deployed)
      -- OR (lsf.device_id = 'Webcam_dev_1' AND lsf.sensor_file_path::text LIKE '%_webcam.avi%')
  )
  -- Uncomment one of these filters:
  -- AND ls.application_version = 'v0.86.0'
  -- AND ls.date >= '2026-04-17'
ORDER BY ls.date, ls.log_session_id, lt.task_id, lsf.device_id;
