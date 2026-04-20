-- Modifications to neurobooth database schema associated with system enhancements

-- These changes can be run at any time BEFORE the associated code changes are applied
-- as it doesn't break anything if it's used for any earlier version and
-- it doesn't break anything if it runs more than once. If those commitments don't hold
-- for some future changes, a separate script will be provided.

-- Each change is commented with the version it is required for

-- The changes are applied in the order required.

-- required for version v0.86.0 and later:
--   ACQ writes log_sensor_file rows at device.start() time with timing
--   fields NULL (to be populated by XDF post-processing). Without this
--   migration the early-write INSERT fails with a NotNullViolation,
--   falling back to split_xdf's INSERT which registers only the HDF5
--   path and leaves the raw video/EDF files unregistered.
ALTER TABLE IF EXISTS public.log_sensor_file
    ALTER COLUMN file_start_time DROP NOT NULL,
    ALTER COLUMN file_end_time   DROP NOT NULL;
