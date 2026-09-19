from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Chunk, Document, IngestionJob, Repository
from app.services.chunking_service import chunk_markdown
from app.services.github_service import (
    GitHubError,
    fetch_doc_files,
    fetch_releases,
    fetch_repository,
    parse_github_url,
)

logger = logging.getLogger(__name__)


def repository_counts(db: Session, repository_id: uuid.UUID) -> tuple[int, int]:
    documents = db.scalar(
        select(func.count()).select_from(Document).where(Document.repository_id == repository_id)
    )
    chunks = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.repository_id == repository_id)
    )
    return int(documents or 0), int(chunks or 0)


def latest_jobs(db: Session, repository_id: uuid.UUID) -> list[IngestionJob]:
    return list(
        db.scalars(
            select(IngestionJob)
            .where(IngestionJob.repository_id == repository_id)
            .order_by(IngestionJob.wave.asc(), IngestionJob.created_at.desc())
        ).all()
    )


def start_import(db: Session, url: str, *, force: bool = False) -> tuple[Repository, IngestionJob, bool]:
    ref = parse_github_url(url)
    repo = db.scalar(select(Repository).where(Repository.owner == ref.owner, Repository.name == ref.name))
    if repo is None:
        meta = fetch_repository(ref)
        repo = Repository(
            owner=meta.ref.owner,
            name=meta.ref.name,
            github_url=meta.html_url,
            default_branch=meta.default_branch,
            description=meta.description,
            stars=meta.stars,
        )
        db.add(repo)
        db.flush()
    else:
        meta = fetch_repository(ref)
        repo.default_branch = meta.default_branch
        repo.description = meta.description
        repo.stars = meta.stars
        repo.github_url = meta.html_url

    existing_wave0 = db.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.repository_id == repo.id,
            IngestionJob.wave == 0,
            IngestionJob.status.in_(["completed", "running"]),
        )
        .order_by(IngestionJob.created_at.desc())
    )
    already_indexed = existing_wave0 is not None and existing_wave0.status == "completed"
    if already_indexed and not force:
        _ensure_wave1_job(db, repo.id)
        db.commit()
        db.refresh(existing_wave0)
        return repo, existing_wave0, True

    job = IngestionJob(
        repository_id=repo.id,
        wave=0,
        status="queued",
        progress={"phase": "queued"},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    db.refresh(repo)
    return repo, job, False


def schedule_wave0(job_id: uuid.UUID) -> None:
    thread = threading.Thread(target=run_wave0, args=(job_id,), name=f"wave0-{job_id}", daemon=True)
    thread.start()


def run_wave0(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if job is None:
            return
        repo = db.get(Repository, job.repository_id)
        if repo is None:
            job.status = "failed"
            job.error = "Repository disappeared before ingest started."
            db.commit()
            return

        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.progress = {"phase": "fetching_github"}
        db.commit()

        meta = fetch_repository(parse_github_url(repo.github_url))
        repo.default_branch = meta.default_branch
        repo.description = meta.description
        repo.stars = meta.stars
        db.commit()

        files, file_stats = fetch_doc_files(
            meta,
            max_files=settings.wave0_max_doc_files,
            max_file_bytes=settings.wave0_max_file_bytes,
        )
        job.progress = {"phase": "indexing_docs", **file_stats}
        db.commit()

        documents_upserted = 0
        chunks_upserted = 0
        for doc_file in files:
            documents_upserted += 1
            chunks_upserted += _upsert_document(
                db,
                repository_id=repo.id,
                source_type=doc_file.source_type,
                external_id=doc_file.path,
                title=_title_from_path(doc_file.path),
                body=doc_file.content,
                source_url=doc_file.source_url,
                extra={"path": doc_file.path},
            )
            if documents_upserted % 10 == 0:
                job.progress = {
                    "phase": "indexing_docs",
                    **file_stats,
                    "documents_upserted": documents_upserted,
                    "chunks_upserted": chunks_upserted,
                }
                db.commit()

        releases = fetch_releases(meta, max_releases=settings.wave0_max_releases)
        for release in releases:
            documents_upserted += 1
            chunks_upserted += _upsert_document(
                db,
                repository_id=repo.id,
                source_type="release",
                external_id=release.external_id,
                title=release.title,
                body=release.body,
                source_url=release.source_url,
                author=release.author,
                created_at=release.created_at,
                extra=release.extra,
            )

        repo.last_synced_at = datetime.now(UTC)
        wave1 = _ensure_wave1_job(db, repo.id)
        job.status = "completed"
        job.finished_at = datetime.now(UTC)
        job.progress = {
            "phase": "complete",
            **file_stats,
            "releases_indexed": len(releases),
            "documents_upserted": documents_upserted,
            "chunks_upserted": chunks_upserted,
            "wave1_job_id": str(wave1.id),
        }
        db.commit()
    except GitHubError as exc:
        _fail_job(db, job_id, str(exc))
    except Exception:
        logger.exception("wave 0 ingest failed for job %s", job_id)
        _fail_job(db, job_id, "Ingestion failed unexpectedly.")
    finally:
        db.close()


def _upsert_document(
    db: Session,
    *,
    repository_id: uuid.UUID,
    source_type: str,
    external_id: str,
    title: str,
    body: str,
    source_url: str | None = None,
    author: str | None = None,
    created_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> int:
    document = db.scalar(
        select(Document).where(
            Document.repository_id == repository_id,
            Document.source_type == source_type,
            Document.external_id == external_id,
        )
    )
    if document is None:
        document = Document(
            repository_id=repository_id,
            source_type=source_type,
            external_id=external_id,
            title=title,
            body=body,
            source_url=source_url,
            author=author,
            created_at=created_at,
            extra=extra or {},
        )
        db.add(document)
        db.flush()
    else:
        document.title = title
        document.body = body
        document.source_url = source_url
        document.author = author
        document.created_at = created_at or document.created_at
        document.extra = extra or {}
        db.execute(delete(Chunk).where(Chunk.document_id == document.id))

    drafts = chunk_markdown(body)
    if not drafts:
        drafts = chunk_markdown(title)
    for draft in drafts:
        db.add(
            Chunk(
                document_id=document.id,
                repository_id=repository_id,
                text=draft.text,
                chunk_index=draft.chunk_index,
                token_count=draft.token_count,
            )
        )
    db.flush()
    return len(drafts)


def _ensure_wave1_job(db: Session, repository_id: uuid.UUID) -> IngestionJob:
    existing = db.scalar(
        select(IngestionJob)
        .where(IngestionJob.repository_id == repository_id, IngestionJob.wave == 1)
        .order_by(IngestionJob.created_at.desc())
    )
    if existing is not None:
        return existing
    job = IngestionJob(
        repository_id=repository_id,
        wave=1,
        status="pending",
        progress={"phase": "queued_for_issues_and_prs"},
    )
    db.add(job)
    db.flush()
    return job


def _fail_job(db: Session, job_id: uuid.UUID, message: str) -> None:
    job = db.get(IngestionJob, job_id)
    if job is None:
        db.rollback()
        return
    job.status = "failed"
    job.error = message
    job.finished_at = datetime.now(UTC)
    job.progress = {**job.progress, "phase": "failed"}
    db.commit()


def _title_from_path(path: str) -> str:
    return path.rsplit("/", 1)[-1]
