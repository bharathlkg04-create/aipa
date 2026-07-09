-- Google Sign-In + Conversations inbox.
-- Run this in the Supabase SQL editor BEFORE deploying the matching app code.

-- 1) Google Sign-In: bind each business to at most one Google account.
--    (Replaces Clerk; the old clerk_user_id column is left in place, unused.)
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS google_user_id text;

-- One business per Google account (partial index so many NULLs are fine).
CREATE UNIQUE INDEX IF NOT EXISTS businesses_google_user_id_uniq
  ON businesses (google_user_id)
  WHERE google_user_id IS NOT NULL;

-- 2) Conversations inbox: remember the customer's display name
--    (Telegram first name / WhatsApp push name) for the dashboard.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS customer_name text;

-- Optional cleanup, ONLY after every user has re-linked via Google:
-- ALTER TABLE businesses DROP COLUMN IF EXISTS clerk_user_id;
