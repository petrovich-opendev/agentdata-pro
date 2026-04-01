"""Add domain_types table, domains.domain_type_id FK, chat_sessions.user_id column.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-31
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create domain_types table
    op.execute("""
        CREATE TABLE domain_types (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            system_prompt TEXT NOT NULL,
            router_prompt TEXT NOT NULL,
            search_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            agent_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            ui_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # 2. Seed BioCoach domain type
    op.execute("""
        INSERT INTO domain_types (id, name, description, system_prompt, router_prompt, search_config, agent_config)
        VALUES (
            'health',
            'BioCoach',
            'Personal AI health advisor',
            'System prompt loaded from file at runtime',
            E'You are an intent classifier. Analyze the user message and determine the intent.\\n\\nRespond ONLY with valid JSON, no other text.\\n\\nPossible intents:\\n- \"general_chat\": general health questions, advice, conversation\\n- \"search\": user wants to find, buy, or compare products, medications, supplements, or services; asks about prices or availability\\n\\nExtract relevant entities (product names, symptoms, topics) into the \"entities\" array.\\n\\nExamples:\\n- \"What vitamins help with sleep?\" -> {\"intent\": \"general_chat\", \"entities\": [\"vitamins\", \"sleep\"]}\\n- \"Where to buy melatonin and how much does it cost?\" -> {\"intent\": \"search\", \"entities\": [\"melatonin\"]}\\n- \"Compare prices for omega-3\" -> {\"intent\": \"search\", \"entities\": [\"omega-3\"]}\\n\\nUser message: ',
            '{"language": "ru", "region": "ru-ru", "max_results": 10, "query_enhancement": {"search": "buy price reviews"}}'::jsonb,
            '{"enabled_agents": ["router", "search"], "models": {"router": "qwen3:14b", "chat": "claude-sonnet-4-20250514"}}'::jsonb
        )
    """)

    # 3. Add domain_type_id FK to domains table
    op.execute("""
        ALTER TABLE domains
        ADD COLUMN domain_type_id TEXT DEFAULT 'health' REFERENCES domain_types(id)
    """)

    # 4. Add user_id to chat_sessions (service.py queries by user_id but column was missing)
    op.execute("""
        ALTER TABLE chat_sessions
        ADD COLUMN user_id UUID REFERENCES users(id)
    """)
    op.execute("""
        CREATE INDEX ix_chat_sessions_user_domain
        ON chat_sessions(user_id, domain_id)
    """)

    # 5. Grant permissions on new table to app role
    op.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE ON domain_types TO biocoach_app
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chat_sessions_user_domain")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE domains DROP COLUMN IF EXISTS domain_type_id")
    op.execute("DROP TABLE IF EXISTS domain_types CASCADE")
