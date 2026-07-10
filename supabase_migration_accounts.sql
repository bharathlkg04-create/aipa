-- Email/password accounts for the dashboard (alongside Google sign-in).
-- Run in the Supabase SQL editor BEFORE deploying the matching app code.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS accounts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name     text NOT NULL,
  email         text NOT NULL,
  password_hash text NOT NULL,
  -- Bearer session secret ("acct_…"), sent as Authorization: Bearer <token>
  account_token text UNIQUE NOT NULL,
  created_at    timestamptz DEFAULT now()
);

-- Emails are unique case-insensitively.
CREATE UNIQUE INDEX IF NOT EXISTS accounts_email_uniq ON accounts (lower(email));

-- One business per account (same rule as Google sign-in).
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS account_id uuid REFERENCES accounts(id);
CREATE UNIQUE INDEX IF NOT EXISTS businesses_account_id_uniq
  ON businesses (account_id)
  WHERE account_id IS NOT NULL;
