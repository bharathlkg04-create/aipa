-- Clerk authentication: bind each business to at most one Clerk user.
-- NULL = not linked yet (legacy owner-token access still works).
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS clerk_user_id text;

-- One business per Clerk user (partial index so many NULLs are fine).
CREATE UNIQUE INDEX IF NOT EXISTS businesses_clerk_user_id_uniq
  ON businesses (clerk_user_id)
  WHERE clerk_user_id IS NOT NULL;
