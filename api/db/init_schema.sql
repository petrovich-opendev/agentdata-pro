-- BioCoach MVP schema
-- Run: psql -U postgres -d biocoach -f init_schema.sql
-- Idempotent: safe to re-run (uses IF NOT EXISTS / OR REPLACE)

BEGIN;

-- ============================================================
-- 1. Application role (used by asyncpg pool via SET ROLE)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'biocoach_app') THEN
        CREATE ROLE biocoach_app NOLOGIN;
    END IF;
END
$$;

-- ============================================================
-- 2. Tables
-- ============================================================

-- Users (minimal, pseudonymous)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT UNIQUE NOT NULL,
    telegram_username TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- Knowledge Domains (one per user for MVP, no domain_type_id per brief)
CREATE TABLE IF NOT EXISTS domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'personal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auth codes (temporary, for Telegram verification)
CREATE TABLE IF NOT EXISTS auth_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT NOT NULL,
    code_hash TEXT NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Refresh tokens
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chat sessions
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

-- Chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 3. Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_auth_codes_chat_id
    ON auth_codes(telegram_chat_id, used, expires_at);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user
    ON refresh_tokens(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_domain
    ON chat_sessions(domain_id, created_at);

CREATE INDEX IF NOT EXISTS idx_messages_session
    ON chat_messages(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_messages_domain
    ON chat_messages(domain_id);

-- Unique: one domain per user (MVP)
CREATE UNIQUE INDEX IF NOT EXISTS idx_domains_owner_unique
    ON domains(owner_id);

CREATE INDEX IF NOT EXISTS idx_domains_owner
    ON domains(owner_id);

-- ============================================================
-- 4. Row Level Security
-- ============================================================

-- domains: isolate by domain id
ALTER TABLE domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE domains FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS domain_isolation ON domains;
CREATE POLICY domain_isolation ON domains
    FOR ALL
    USING (id::text = current_setting('app.current_domain', true));

-- chat_sessions: isolate by domain_id
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS session_isolation ON chat_sessions;
CREATE POLICY session_isolation ON chat_sessions
    FOR ALL
    USING (domain_id::text = current_setting('app.current_domain', true));

-- chat_messages: isolate by domain_id
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS message_isolation ON chat_messages;
CREATE POLICY message_isolation ON chat_messages
    FOR ALL
    USING (domain_id::text = current_setting('app.current_domain', true));

-- ============================================================
-- 5. GRANT permissions for biocoach_app role
-- ============================================================

-- Tables: full CRUD for app role
GRANT SELECT, INSERT, UPDATE, DELETE ON users TO biocoach_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON domains TO biocoach_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_codes TO biocoach_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON refresh_tokens TO biocoach_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sessions TO biocoach_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_messages TO biocoach_app;

-- Allow SET LOCAL for RLS context
GRANT SET ON PARAMETER app.current_domain TO biocoach_app;

COMMIT;
