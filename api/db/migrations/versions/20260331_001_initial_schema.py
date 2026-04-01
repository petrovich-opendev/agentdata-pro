"""Initial schema: users, domains, auth_codes, refresh_tokens, chat_sessions, chat_messages + RLS.

Revision ID: 0001
Revises: None
Create Date: 2026-03-31
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create application role with RLS enforced
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'biocoach_app') THEN
                CREATE ROLE biocoach_app NOLOGIN NOBYPASSRLS;
            END IF;
        END $$
    """)
    op.execute("GRANT biocoach_app TO biocoach")

    # 2. users
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_chat_id BIGINT UNIQUE NOT NULL,
            telegram_username TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login_at TIMESTAMPTZ
        )
    """)

    # 3. domains
    op.execute("""
        CREATE TABLE domains (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id UUID NOT NULL REFERENCES users(id),
            name TEXT NOT NULL DEFAULT 'personal',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (owner_id)
        )
    """)

    # 4. auth_codes
    op.execute("""
        CREATE TABLE auth_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_chat_id BIGINT NOT NULL,
            code_hash TEXT NOT NULL,
            attempts INT NOT NULL DEFAULT 0,
            expires_at TIMESTAMPTZ NOT NULL,
            used BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_auth_codes_lookup
        ON auth_codes(telegram_chat_id, used, expires_at)
    """)

    # 5. refresh_tokens
    op.execute("""
        CREATE TABLE refresh_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_refresh_tokens_user_id
        ON refresh_tokens(user_id)
    """)

    # 6. chat_sessions
    op.execute("""
        CREATE TABLE chat_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            domain_id UUID NOT NULL REFERENCES domains(id),
            title TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX ix_chat_sessions_domain_created
        ON chat_sessions(domain_id, created_at)
    """)

    # 7. chat_messages
    op.execute("""
        CREATE TABLE chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES chat_sessions(id),
            domain_id UUID NOT NULL REFERENCES domains(id),
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_chat_messages_session_created
        ON chat_messages(session_id, created_at)
    """)
    op.execute("""
        CREATE INDEX ix_chat_messages_domain_id
        ON chat_messages(domain_id)
    """)

    # 8. Enable and force RLS on domain-scoped tables
    for table in ("domains", "chat_sessions", "chat_messages"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # 9. RLS policies — filter by app.current_domain
    op.execute("""
        CREATE POLICY domain_isolation ON domains
            FOR ALL TO biocoach_app
            USING (id::text = current_setting('app.current_domain', true))
            WITH CHECK (id::text = current_setting('app.current_domain', true))
    """)
    op.execute("""
        CREATE POLICY domain_isolation ON chat_sessions
            FOR ALL TO biocoach_app
            USING (domain_id::text = current_setting('app.current_domain', true))
            WITH CHECK (domain_id::text = current_setting('app.current_domain', true))
    """)
    op.execute("""
        CREATE POLICY domain_isolation ON chat_messages
            FOR ALL TO biocoach_app
            USING (domain_id::text = current_setting('app.current_domain', true))
            WITH CHECK (domain_id::text = current_setting('app.current_domain', true))
    """)

    # 10. Grant permissions to app role
    op.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE
        ON ALL TABLES IN SCHEMA public
        TO biocoach_app
    """)


def downgrade() -> None:
    # Drop policies
    for table in ("chat_messages", "chat_sessions", "domains"):
        op.execute(f"DROP POLICY IF EXISTS domain_isolation ON {table}")

    # Revoke grants
    op.execute("""
        REVOKE SELECT, INSERT, UPDATE, DELETE
        ON ALL TABLES IN SCHEMA public
        FROM biocoach_app
    """)

    # Drop tables in reverse order
    for table in (
        "chat_messages",
        "chat_sessions",
        "refresh_tokens",
        "auth_codes",
        "domains",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Drop role
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'biocoach_app') THEN
                DROP ROLE biocoach_app;
            END IF;
        END $$
    """)
