from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import IngestionJob, Repository
from app.schemas import (
    ImportRequest,
    ImportResponse,
    JobOut,
    RepositoryDetail,
    RepositoryOut,
    SearchRequest,
    SearchResponse,
)
from app.services.github_service import GitHubError
from app.services.ingestion_service import (
    latest_jobs,
    repository_counts,
    schedule_wave0,
    start_import,
)
from app.services.retrieval_service import coverage_for, search_repository

router = APIRouter()


def _repo_out(db: Session, repo: Repository) -> RepositoryOut:
    documents, chunks = repository_counts(db, repo.id)
    return RepositoryOut(
        id=repo.id,
        owner=repo.owner,
        name=repo.name,
        github_url=repo.github_url,
        default_branch=repo.default_branch,
        description=repo.description,
        stars=repo.stars,
        last_synced_at=repo.last_synced_at,
        document_count=documents,
        chunk_count=chunks,
    )


@router.post("/repositories", response_model=ImportResponse)
def import_repository(
    payload: ImportRequest,
    db: Session = Depends(get_db),
) -> ImportResponse:
    try:
        repo, job, already_indexed = start_import(db, payload.url, force=payload.force)
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if job.status == "queued":
        schedule_wave0(job.id)

    return ImportResponse(
        repository=_repo_out(db, repo),
        job=JobOut.model_validate(job),
        already_indexed=already_indexed,
    )


@router.get("/repositories/{repository_id}", response_model=RepositoryDetail)
def get_repository(repository_id: uuid.UUID, db: Session = Depends(get_db)) -> RepositoryDetail:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    jobs = latest_jobs(db, repo.id)
    unique: dict[int, IngestionJob] = {}
    for job in jobs:
        unique.setdefault(job.wave, job)
    return RepositoryDetail(
        repository=_repo_out(db, repo),
        jobs=[JobOut.model_validate(job) for job in unique.values()],
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobOut.model_validate(job)


@router.post("/repositories/{repository_id}/search", response_model=SearchResponse)
def search(repository_id: uuid.UUID, payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    results = search_repository(db, repository_id, payload.query, limit=payload.limit)
    return SearchResponse(
        query=payload.query,
        repository_id=repository_id,
        coverage=coverage_for(db, repository_id),
        results=results,
    )
