# RepoLens

RepoLens is a planned shared knowledge platform for GitHub repositories, bringing source code, documentation, issues, pull requests, comments, releases, and development history into one searchable place.

## Fresh start

The previous local setup has been cleared. No application, ingestion pipeline, search index, generated answers, evaluations, or deployment is implemented in this checkout.

## Product direction

- Index public repositories once and reuse the index across users.
- Connect source-code structure with documentation and development discussions.
- Answer questions using relevant evidence with citations pinned to the indexed version.
- Keep repository knowledge fresh and expose indexing coverage.
- Evaluate answer quality, citation accuracy, retrieval quality, latency, and cost against an LLM connected directly to the GitHub API.

These are intended capabilities, not implemented claims. Architecture, integrations, and deployment will be chosen during the rebuild.

Git history and existing branches remain available. Local credentials are retained in the ignored `.env`; review them when configuring integrations.
