# RepoLens

RepoLens is a search engine for GitHub history. It indexes documentation and releases into PostgreSQL, then answers engineering questions with cited repository evidence — not a live `gh` + LLM loop.

This first slice:

1. Accepts a public GitHub URL
2. Ingests README, docs, ADRs, changelogs, and releases (wave 0)
3. Makes that corpus keyword-searchable immediately
4. Queues a wave 1 job for issues/PRs (not fetched yet)

## Run locally

```bash
cp .env.example .env
docker compose up -d db
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. Set `GITHUB_TOKEN` in `.env` for authenticated GitHub API access (unauthenticated ingest is limited to 60 requests/hour).

## API

- `POST /v1/repositories` — start wave 0 ingest
- `GET /v1/repositories/{id}` — repo + job coverage
- `GET /v1/jobs/{id}` — ingest progress
- `POST /v1/repositories/{id}/search` — keyword search over indexed chunks
