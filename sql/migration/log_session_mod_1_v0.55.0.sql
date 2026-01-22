-- Modifications to neurobooth database associated with system enhancements

-- The current version can be run at any time as it doesn't break anything if it's run before the code changes
-- and it doesn't break anything if it runs more than once. If that commitment doesn't hold for some future
-- changes, a separate script will be provided.

-- Each change is commented with the version it is required for

-- The changes are applied in the order required.

ALTER TABLE IF EXISTS public.log_session
    -- required for changes in version v0.55.0 and later
    ADD COLUMN IF NOT EXISTS application_version character varying,
    -- required for version v0.56 and later
    ADD COLUMN IF NOT EXISTS config_version character varying;