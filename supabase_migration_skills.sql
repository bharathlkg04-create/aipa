-- AI'PA skills catalog migration (2000+ skills, vector retrieval)
-- Run this once in the Supabase SQL editor AFTER supabase_migration.sql

-- pgvector ships with Supabase; just enable it
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE skills ADD COLUMN IF NOT EXISTS slug        TEXT UNIQUE;
ALTER TABLE skills ADD COLUMN IF NOT EXISTS category    TEXT NOT NULL DEFAULT 'general';
ALTER TABLE skills ADD COLUMN IF NOT EXISTS industry    TEXT NOT NULL DEFAULT 'generic';
ALTER TABLE skills ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE skills ADD COLUMN IF NOT EXISTS embedding   vector(1536);
ALTER TABLE skills ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ DEFAULT NOW();

-- Pinned skills are always injected into the prompt regardless of relevance
ALTER TABLE business_skills ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_skills_industry ON skills (industry);
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills (category);
CREATE INDEX IF NOT EXISTS idx_business_skills_business ON business_skills (business_id) WHERE is_enabled;

-- HNSW works on empty tables and needs no tuning as the catalog grows
CREATE INDEX IF NOT EXISTS idx_skills_embedding ON skills
    USING hnsw (embedding vector_cosine_ops);

-- Owner token: proves ownership of a business on skill write endpoints.
-- Returned once by POST /api/setup; sent back as the X-Owner-Token header.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
ALTER TABLE businesses ADD COLUMN IF NOT EXISTS owner_token TEXT UNIQUE;
UPDATE businesses
SET owner_token = encode(gen_random_bytes(24), 'hex')
WHERE owner_token IS NULL;
