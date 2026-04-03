"""Chat folders and full-text search.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. chat_folders table
    op.execute("""
        CREATE TABLE chat_folders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            domain_id UUID NOT NULL REFERENCES domains(id),
            name TEXT NOT NULL,
            emoji TEXT,
            color TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_chat_folders_domain
        ON chat_folders(domain_id, sort_order)
    """)

    # 2. RLS on chat_folders (same pattern as chat_sessions)
    op.execute("ALTER TABLE chat_folders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chat_folders FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY domain_isolation ON chat_folders
            FOR ALL TO biocoach_app
            USING (domain_id::text = current_setting('app.current_domain', true))
            WITH CHECK (domain_id::text = current_setting('app.current_domain', true))
    """)
    op.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_folders TO biocoach_app
    """)

    # 3. Add folder_id to chat_sessions
    op.execute("""
        ALTER TABLE chat_sessions
        ADD COLUMN folder_id UUID REFERENCES chat_folders(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX ix_chat_sessions_folder
        ON chat_sessions(folder_id)
        WHERE folder_id IS NOT NULL AND deleted_at IS NULL
    """)

    # 4. Full-text search vector on chat_messages
    op.execute("""
        ALTER TABLE chat_messages ADD COLUMN search_vector tsvector
    """)
    op.execute("""
        CREATE INDEX ix_chat_messages_search
        ON chat_messages USING GIN(search_vector)
    """)

    # 5. Trigger to auto-populate search_vector
    op.execute("""
        CREATE OR REPLACE FUNCTION chat_messages_search_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                to_tsvector('russian', COALESCE(NEW.content, '')) ||
                to_tsvector('english', COALESCE(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_chat_messages_search
            BEFORE INSERT OR UPDATE OF content ON chat_messages
            FOR EACH ROW EXECUTE FUNCTION chat_messages_search_trigger()
    """)

    # 6. Backfill existing messages
    op.execute("""
        UPDATE chat_messages SET search_vector =
            to_tsvector('russian', COALESCE(content, '')) ||
            to_tsvector('english', COALESCE(content, ''))
    """)

    # 7. Title search vector on chat_sessions
    op.execute("""
        ALTER TABLE chat_sessions ADD COLUMN title_search tsvector
    """)
    op.execute("""
        CREATE INDEX ix_chat_sessions_title_search
        ON chat_sessions USING GIN(title_search)
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION chat_sessions_title_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.title_search :=
                to_tsvector('russian', COALESCE(NEW.title, '')) ||
                to_tsvector('english', COALESCE(NEW.title, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_chat_sessions_title
            BEFORE INSERT OR UPDATE OF title ON chat_sessions
            FOR EACH ROW EXECUTE FUNCTION chat_sessions_title_trigger()
    """)

    # 8. Backfill session titles
    op.execute("""
        UPDATE chat_sessions SET title_search =
            to_tsvector('russian', COALESCE(title, '')) ||
            to_tsvector('english', COALESCE(title, ''))
    """)


def downgrade() -> None:
    # Remove triggers
    op.execute("DROP TRIGGER IF EXISTS trg_chat_sessions_title ON chat_sessions")
    op.execute("DROP FUNCTION IF EXISTS chat_sessions_title_trigger()")
    op.execute("DROP TRIGGER IF EXISTS trg_chat_messages_search ON chat_messages")
    op.execute("DROP FUNCTION IF EXISTS chat_messages_search_trigger()")

    # Remove columns
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS title_search")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS folder_id")

    # Drop RLS and table
    op.execute("DROP POLICY IF EXISTS domain_isolation ON chat_folders")
    op.execute("DROP TABLE IF EXISTS chat_folders CASCADE")
