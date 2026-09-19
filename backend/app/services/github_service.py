from __future__ import annotations

import io
import re
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

IGNORE_DIR_PARTS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "third_party",
    "vendor",
}

DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".adr"}
PRIORITY_NAMES = {
    "readme",
    "changelog",
    "history",
    "contributing",
    "code_of_conduct",
    "security",
    "architecture",
}


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


@dataclass
class RepoMetadata:
    ref: RepoRef
    default_branch: str
    description: str | None
    stars: int
    html_url: str
    node_id: str | None


@dataclass
class DocFile:
    path: str
    content: str
    source_type: str
    source_url: str


@dataclass
class ReleaseDoc:
    external_id: str
    title: str
    body: str
    source_url: str
    author: str | None
    created_at: datetime | None
    extra: dict[str, Any]


class GitHubError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def parse_github_url(raw: str) -> RepoRef:
    value = raw.strip()
    match = GITHUB_URL_RE.match(value)
    if not match:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        if parsed.netloc.replace("www.", "") != "github.com":
            raise GitHubError("Enter a public GitHub repository URL.", status_code=400)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise GitHubError("Enter a URL like https://github.com/owner/repo.", status_code=400)
        owner, name = parts[0], parts[1].removesuffix(".git")
    else:
        owner, name = match.group("owner"), match.group("name")

    if owner.lower() in {"orgs", "users", "settings", "marketplace", "topics", "search"}:
        raise GitHubError("That GitHub URL is not a repository.", status_code=400)
    return RepoRef(owner=owner, name=name)


def classify_doc_path(path: str) -> str | None:
    lowered = path.lower()
    parts = lowered.split("/")
    if any(part in IGNORE_DIR_PARTS for part in parts):
        return None

    filename = parts[-1]
    stem, _, ext = filename.partition(".")
    ext = f".{ext}" if ext else ""
    if ext and ext not in DOC_EXTENSIONS and filename not in {"dockerfile"}:
        if not any(filename.startswith(name) for name in PRIORITY_NAMES):
            return None

    if "adr" in parts or filename.startswith("adr"):
        return "adr"
    if filename.startswith("readme"):
        return "readme"
    if filename.startswith("changelog") or filename.startswith("history"):
        return "changelog"
    if any(part in {"docs", "doc", "documentation"} for part in parts[:-1]):
        return "markdown"
    if ext in DOC_EXTENSIONS:
        return "markdown"
    return None


def doc_priority(path: str) -> int:
    lowered = path.lower()
    if lowered in {"readme.md", "readme.rst", "readme"}:
        return 0
    if lowered.startswith("docs/") or lowered.startswith("doc/"):
        return 1
    if "adr" in lowered.split("/"):
        return 2
    if lowered.startswith("changelog"):
        return 3
    return 4


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RepoLens",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def _request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    for attempt in range(5):
        response = client.request(method, url, headers=_headers(), **kwargs)
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        retry_after = response.headers.get("retry-after")

        if response.status_code in {403, 429}:
            message = response.text[:300]
            if remaining == "0" and reset:
                wait_for = max(1, int(reset) - int(time.time()))
                if attempt == 4:
                    raise GitHubError(
                        "GitHub rate limited this import. Set GITHUB_TOKEN on the server and retry.",
                        status_code=429,
                    )
                time.sleep(min(wait_for, 60))
                continue
            if retry_after:
                time.sleep(min(int(retry_after), 60))
                continue
            if "rate limit" in message.lower():
                raise GitHubError(
                    "GitHub rate limited this import. Set GITHUB_TOKEN on the server and retry.",
                    status_code=429,
                )
        if response.status_code == 404:
            raise GitHubError("That repository was not found or is not public.", status_code=404)
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API error ({response.status_code}).", status_code=502)
        return response
    raise GitHubError("GitHub API did not respond after retries.", status_code=502)


def fetch_repository(ref: RepoRef) -> RepoMetadata:
    with httpx.Client(base_url=settings.github_api_base, timeout=30.0, follow_redirects=True) as client:
        response = _request(client, "GET", f"/repos/{ref.owner}/{ref.name}")
        payload = response.json()
        return RepoMetadata(
            ref=ref,
            default_branch=payload.get("default_branch") or "main",
            description=payload.get("description"),
            stars=int(payload.get("stargazers_count") or 0),
            html_url=payload.get("html_url") or ref.html_url,
            node_id=payload.get("node_id"),
        )


def fetch_doc_files(meta: RepoMetadata, *, max_files: int, max_file_bytes: int) -> tuple[list[DocFile], dict[str, Any]]:
    archive_url = f"{settings.github_api_base}/repos/{meta.ref.owner}/{meta.ref.name}/tarball/{meta.default_branch}"
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = _request(client, "GET", archive_url)

    selected: list[DocFile] = []
    skipped = 0
    candidates: list[tuple[int, str, bytes]] = []

    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            path = _strip_archive_prefix(member.name)
            if not path or classify_doc_path(path) is None:
                continue
            if member.size > max_file_bytes:
                skipped += 1
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            if b"\x00" in raw[:1024]:
                continue
            candidates.append((doc_priority(path), path, raw))

    candidates.sort(key=lambda item: (item[0], item[1]))
    for _, path, raw in candidates:
        if len(selected) >= max_files:
            skipped += 1
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        source_type = classify_doc_path(path) or "markdown"
        selected.append(
            DocFile(
                path=path,
                content=text,
                source_type=source_type,
                source_url=f"{meta.html_url}/blob/{meta.default_branch}/{path}",
            )
        )

    return selected, {
        "docs_indexed": len(selected),
        "docs_skipped": skipped,
        "docs_found": len(candidates),
    }


def fetch_releases(meta: RepoMetadata, *, max_releases: int) -> list[ReleaseDoc]:
    with httpx.Client(base_url=settings.github_api_base, timeout=30.0, follow_redirects=True) as client:
        response = _request(
            client,
            "GET",
            f"/repos/{meta.ref.owner}/{meta.ref.name}/releases",
            params={"per_page": min(max_releases, 100)},
        )
    releases: list[ReleaseDoc] = []
    for item in response.json()[:max_releases]:
        body = item.get("body") or ""
        tag = item.get("tag_name") or "release"
        releases.append(
            ReleaseDoc(
                external_id=str(item.get("node_id") or item.get("id") or tag),
                title=item.get("name") or tag,
                body=body or tag,
                source_url=item.get("html_url") or f"{meta.html_url}/releases/tag/{tag}",
                author=(item.get("author") or {}).get("login"),
                created_at=_parse_dt(item.get("published_at") or item.get("created_at")),
                extra={"tag": tag, "prerelease": bool(item.get("prerelease"))},
            )
        )
    return releases


def _strip_archive_prefix(name: str) -> str:
    parts = name.split("/", 1)
    return parts[1] if len(parts) == 2 else name


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
