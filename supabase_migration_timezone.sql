-- Per-business timezone for the agent's date/time awareness.
-- IANA name, e.g. 'Asia/Kolkata'; NULL means UTC.
ALTER TABLE boss_config ADD COLUMN IF NOT EXISTS timezone text;
