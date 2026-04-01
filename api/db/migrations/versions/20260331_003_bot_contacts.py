"""Add bot_contacts table for telegram username -> chat_id mapping.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-31
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE bot_contacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_chat_id BIGINT UNIQUE NOT NULL,
            telegram_username TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX ix_bot_contacts_username
        ON bot_contacts(lower(telegram_username))
    """)
    op.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE
        ON bot_contacts TO biocoach_app
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bot_contacts CASCADE")
