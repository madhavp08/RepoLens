"""initial schema for repositories, documents, chunks, jobs

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE TABLE repositories (
            id UUID PRIMARY KEY,
            owner TEXT NOT NULL,
            name TEXT NOT NULL,
            github_url TEXT NOT NULL,
            default_branch TEXT,
            description TEXT,
            stars INTEGER NOT NULL DEFAULT 0,
            last_synced_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_repositories_owner_name UNIQUE (owner, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE documents (
            id UUID PRIMARY KEY,
            repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_url TEXT,
            author TEXT,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_documents_repo_source_external
                UNIQUE (repository_id, source_type, external_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            token_count INTEGER NOT NULL,
            tsv tsvector GENERATED ALWAYS AS
                (to_tsvector('english', coalesce(text, ''))) STORED,
            CONSTRAINT uq_chunks_document_index UNIQUE (document_id, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX ix_chunks_repository_id ON chunks (repository_id)")
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING GIN (tsv)")
    op.execute("CREATE INDEX ix_chunks_text_trgm ON chunks USING GIN (text gin_trgm_ops)")
    op.execute(
        """
        CREATE TABLE ingestion_jobs (
            id UUID PRIMARY KEY,
            repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            wave INTEGER NOT NULL,
            status TEXT NOT NULL,
            cursor TEXT,
            watermark TIMESTAMPTZ,
            progress JSONB NOT NULL DEFAULT '{}'::jsonb,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX ix_ingestion_jobs_repository_id ON ingestion_jobs (repository_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_jobs")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS repositories")
