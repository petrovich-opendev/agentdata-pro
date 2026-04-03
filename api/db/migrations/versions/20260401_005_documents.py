"""Document upload and biomarker extraction tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. documents table — stores uploaded file metadata and parsed text
    op.execute("""
        CREATE TABLE documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            domain_id UUID NOT NULL REFERENCES domains(id),
            session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'application/pdf',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                'pending', 'parsing', 'extracting', 'done', 'error'
            )),
            parsed_text TEXT,
            page_count INTEGER,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_documents_domain ON documents(domain_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX ix_documents_session ON documents(session_id)
        WHERE session_id IS NOT NULL
    """)

    # 2. RLS on documents
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY domain_isolation ON documents
            FOR ALL TO biocoach_app
            USING (domain_id::text = current_setting('app.current_domain', true))
            WITH CHECK (domain_id::text = current_setting('app.current_domain', true))
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO biocoach_app")

    # 3. document_biomarkers table — extracted biomarker values
    op.execute("""
        CREATE TABLE document_biomarkers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            domain_id UUID NOT NULL REFERENCES domains(id),
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            unit TEXT,
            ref_range_min NUMERIC,
            ref_range_max NUMERIC,
            ref_range_text TEXT,
            status TEXT CHECK (status IN ('normal', 'low', 'high', 'critical', 'unknown')),
            category TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_document_biomarkers_doc ON document_biomarkers(document_id)
    """)
    op.execute("""
        CREATE INDEX ix_document_biomarkers_domain ON document_biomarkers(domain_id)
    """)

    # 4. RLS on document_biomarkers
    op.execute("ALTER TABLE document_biomarkers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_biomarkers FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY domain_isolation ON document_biomarkers
            FOR ALL TO biocoach_app
            USING (domain_id::text = current_setting('app.current_domain', true))
            WITH CHECK (domain_id::text = current_setting('app.current_domain', true))
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON document_biomarkers TO biocoach_app")

    # 5. updated_at trigger for documents
    op.execute("""
        CREATE OR REPLACE FUNCTION update_documents_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_documents_updated_at
            BEFORE UPDATE ON documents
            FOR EACH ROW EXECUTE FUNCTION update_documents_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents")
    op.execute("DROP FUNCTION IF EXISTS update_documents_updated_at()")
    op.execute("DROP POLICY IF EXISTS domain_isolation ON document_biomarkers")
    op.execute("DROP TABLE IF EXISTS document_biomarkers CASCADE")
    op.execute("DROP POLICY IF EXISTS domain_isolation ON documents")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
