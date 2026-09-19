from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ImportRequest(BaseModel):
    url: str = Field(min_length=3, max_length=500)
    force: bool = False


class RepositoryOut(BaseModel):
    id: uuid.UUID
    owner: str
    name: str
    github_url: str
    default_branch: str | None
    description: str | None
    stars: int
    last_synced_at: datetime | None
    document_count: int
    chunk_count: int

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    wave: int
    status: str
    progress: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ImportResponse(BaseModel):
    repository: RepositoryOut
    job: JobOut
    already_indexed: bool


class RepositoryDetail(BaseModel):
    repository: RepositoryOut
    jobs: list[JobOut]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=50)


class SourceCard(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    source_type: str
    title: str
    source_url: HttpUrl | str | None
    excerpt: str
    rank: float
    extra: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    repository_id: uuid.UUID
    coverage: dict[str, Any]
    results: list[SourceCard]
