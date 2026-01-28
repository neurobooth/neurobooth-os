-- Modifications to neurobooth database schema associated with system enhancements

-- These changes can be run at any time BEFORE the associated code changes are applied
-- as it doesn't break anything if it's used for any earlier version and
-- it doesn't break anything if it runs more than once. If those commitments don't hold
-- for some future changes, a separate script will be provided.

-- Each change is commented with the version it is required for

-- The changes are applied in the order required.

ALTER TABLE IF EXISTS public.log_session

    -- required for version v0.55.0 and later
    ADD COLUMN IF NOT EXISTS application_version character varying,

    -- required for version v0.56.0 and later
    ADD COLUMN IF NOT EXISTS config_version character varying;