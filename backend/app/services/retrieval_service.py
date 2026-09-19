from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import SourceCard


def search_repository(db: Session, repository_id: uuid.UUID, query: str, *, limit: int = 20) -> list[SourceCard]:
    sql = text(
        """
        WITH q AS (
            SELECT
                websearch_to_tsquery('english', :query) AS tsq,
                :raw_query AS raw
        )
        SELECT
            c.id AS chunk_id,
            d.id AS document_id,
            d.source_type,
            d.title,
            d.source_url,
            d.metadata AS extra,
            ts_rank_cd(c.tsv, q.tsq) AS fts_rank,
            similarity(c.text, q.raw) AS trigram_rank,
            ts_headline(
                'english',
                c.text,
                q.tsq,
                'StartSel=<<, StopSel=>>, MaxWords=40, MinWords=12, HighlightAll=false'
            ) AS excerpt
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        CROSS JOIN q
        WHERE c.repository_id = :repository_id
          AND (
                (q.tsq IS NOT NULL AND c.tsv @@ q.tsq)
                OR c.text ILIKE '%' || q.raw || '%'
              )
        ORDER BY (ts_rank_cd(c.tsv, q.tsq) * 2) + similarity(c.text, q.raw) DESC
        LIMIT :limit
        """
    )
    rows = db.execute(
        sql,
        {
            "query": query,
            "raw_query": query,
            "repository_id": str(repository_id),
            "limit": limit,
        },
    ).mappings()

    cards: list[SourceCard] = []
    for row in rows:
        excerpt = row["excerpt"] or ""
        excerpt = excerpt.replace("<<", "").replace(">>", "")
        rank = float(row["fts_rank"] or 0) * 2 + float(row["trigram_rank"] or 0)
        cards.append(
            SourceCard(
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                source_type=row["source_type"],
                title=row["title"],
                source_url=row["source_url"],
                excerpt=excerpt.strip() or query,
                rank=rank,
                extra=row["extra"] or {},
            )
        )
    return cards


def coverage_for(db: Session, repository_id: uuid.UUID) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT wave, status, progress
            FROM ingestion_jobs
            WHERE repository_id = :repository_id
            ORDER BY wave ASC, created_at DESC
            """
        ),
        {"repository_id": str(repository_id)},
    ).mappings()
    seen: set[int] = set()
    coverage: dict[str, Any] = {"waves": []}
    for row in rows:
        if row["wave"] in seen:
            continue
        seen.add(row["wave"])
        coverage["waves"].append(
            {"wave": row["wave"], "status": row["status"], "progress": row["progress"]}
        )
    document_count = db.scalar(
        text("SELECT count(*) FROM documents WHERE repository_id = :id"),
        {"id": str(repository_id)},
    )
    coverage["document_count"] = int(document_count or 0)
    return coverage
