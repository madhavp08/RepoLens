"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  getRepository,
  importRepository,
  searchRepository,
  type Job,
  type Repository,
  type SearchResponse,
} from "@/lib/api";

export default function HomePage() {
  const [url, setUrl] = useState("https://github.com/pallets/flask");
  const [query, setQuery] = useState("Why was this project created?");
  const [importing, setImporting] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repository, setRepository] = useState<Repository | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);

  const wave0 = jobs.find((job) => job.wave === 0);
  const wave1 = jobs.find((job) => job.wave === 1);
  const searchable = (repository?.document_count ?? 0) > 0;

  useEffect(() => {
    if (!repository || !activeJobId) return;
    if (wave0 && (wave0.status === "completed" || wave0.status === "failed")) return;

    const timer = window.setInterval(async () => {
      try {
        const detail = await getRepository(repository.id);
        setRepository(detail.repository);
        setJobs(detail.jobs);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not refresh ingest status.");
      }
    }, 1500);

    return () => window.clearInterval(timer);
  }, [repository, activeJobId, wave0]);

  const coverageLabel = useMemo(() => {
    if (!repository) return "Paste a public repository to build a searchable index.";
    const docs = `${repository.document_count} source${repository.document_count === 1 ? "" : "s"}`;
    const wave0Status = wave0?.status ?? "queued";
    const wave1Status = wave1?.status ?? "pending";
    return `${docs} indexed · wave 0 ${wave0Status} · wave 1 ${wave1Status}`;
  }, [repository, wave0, wave1]);

  async function onImport(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResults(null);
    setImporting(true);
    try {
      const imported = await importRepository(url.trim());
      setRepository(imported.repository);
      setJobs([imported.job]);
      setActiveJobId(imported.job.id);
      const detail = await getRepository(imported.repository.id);
      setRepository(detail.repository);
      setJobs(detail.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed.");
    } finally {
      setImporting(false);
    }
  }

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    if (!repository) return;
    setError(null);
    setSearching(true);
    try {
      const response = await searchRepository(repository.id, query.trim());
      setResults(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-10 font-[family-name:var(--font-sans)]">
      <header className="mb-12 flex flex-col gap-6 border-b border-[var(--line)] pb-10 md:flex-row md:items-end md:justify-between">
        <div className="max-w-xl">
          <p className="mb-3 font-[family-name:var(--font-mono)] text-xs tracking-[0.22em] text-[var(--copper)] uppercase">
            Persistent index · keyword search
          </p>
          <h1 className="font-[family-name:var(--font-serif)] text-5xl leading-[1.05] tracking-tight text-[var(--ink)]">
            RepoLens
          </h1>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-[var(--muted)]">
            Search a repository&apos;s docs and releases as evidence. The chatbot is optional later.
            The index is the product.
          </p>
        </div>
        <p className="max-w-sm text-sm leading-6 text-[var(--muted)]">
          Wave 0 indexes README, markdown, ADRs, changelogs, and releases. Issues and pull requests
          are queued as wave 1, not fetched live per question.
        </p>
      </header>

      <section className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="space-y-8">
          <form onSubmit={onImport} className="rounded-2xl border border-[var(--line)] bg-[var(--bg-raised)] p-5">
            <label htmlFor="repo-url" className="mb-2 block text-sm text-[var(--muted)]">
              Public GitHub repository
            </label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                id="repo-url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://github.com/owner/repo"
                className="min-w-0 flex-1 rounded-xl border border-[var(--line)] bg-[#14110d] px-4 py-3 font-[family-name:var(--font-mono)] text-sm outline-none focus:border-[var(--copper)]"
              />
              <button
                type="submit"
                disabled={importing}
                className="rounded-xl bg-[var(--copper)] px-5 py-3 text-sm font-medium text-[#1a120a] disabled:opacity-60"
              >
                {importing ? "Indexing…" : "Index repo"}
              </button>
            </div>
          </form>

          <form onSubmit={onSearch} className="rounded-2xl border border-[var(--line)] bg-[var(--bg-raised)] p-5">
            <label htmlFor="query" className="mb-2 block text-sm text-[var(--muted)]">
              Search the indexed evidence
            </label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                id="query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                disabled={!searchable}
                className="min-w-0 flex-1 rounded-xl border border-[var(--line)] bg-[#14110d] px-4 py-3 text-base outline-none focus:border-[var(--copper)] disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!searchable || searching}
                className="rounded-xl border border-[var(--line)] px-5 py-3 text-sm font-medium text-[var(--ink)] disabled:opacity-50"
              >
                {searching ? "Searching…" : "Search"}
              </button>
            </div>
            {!searchable && (
              <p className="mt-3 text-sm text-[var(--muted)]">
                Search unlocks as soon as wave 0 writes the first documents.
              </p>
            )}
          </form>

          {error && (
            <p className="rounded-xl border border-[var(--bad)]/40 bg-[var(--bad)]/10 px-4 py-3 text-sm text-[#f0c2b6]">
              {error}
            </p>
          )}

          <ResultsList results={results} />
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-[var(--line)] bg-[var(--bg-raised)] p-5">
            <h2 className="font-[family-name:var(--font-serif)] text-2xl">Coverage</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{coverageLabel}</p>
            {repository && (
              <a
                href={repository.github_url}
                className="mt-4 inline-block font-[family-name:var(--font-mono)] text-sm text-[var(--copper)]"
              >
                {repository.owner}/{repository.name}
              </a>
            )}
            <ul className="mt-5 space-y-3">
              <WaveRow
                title="Wave 0 · docs and releases"
                job={wave0}
                fallback="Waiting for a repository URL."
              />
              <WaveRow
                title="Wave 1 · issues and PRs"
                job={wave1}
                fallback="Queued after wave 0. Not a live GitHub search."
              />
            </ul>
          </div>
        </aside>
      </section>
    </main>
  );
}

function WaveRow({ title, job, fallback }: { title: string; job?: Job; fallback: string }) {
  const status = job?.status ?? "idle";
  const progress = job?.progress ?? {};
  const detail = job
    ? Object.entries(progress)
        .filter(([key]) => key !== "phase")
        .slice(0, 4)
        .map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`)
        .join(" · ")
    : fallback;

  return (
    <li className="border-t border-[var(--line)] pt-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm">{title}</p>
        <span className="font-[family-name:var(--font-mono)] text-xs text-[var(--copper)]">{status}</span>
      </div>
      <p className="mt-1 text-sm text-[var(--muted)]">{detail || fallback}</p>
      {job?.error && <p className="mt-1 text-sm text-[#f0c2b6]">{job.error}</p>}
    </li>
  );
}

function ResultsList({ results }: { results: SearchResponse | null }) {
  if (!results) return null;
  if (results.results.length === 0) {
    return (
      <div className="rounded-2xl border border-[var(--line)] px-5 py-8 text-[var(--muted)]">
        No indexed evidence matched that query. RepoLens will not invent an answer.
      </div>
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex items-end justify-between">
        <h2 className="font-[family-name:var(--font-serif)] text-3xl">Sources</h2>
        <p className="text-sm text-[var(--muted)]">{results.results.length} ranked chunks</p>
      </div>
      <ol className="space-y-3">
        {results.results.map((card) => (
          <li key={card.chunk_id} className="rounded-2xl border border-[var(--line)] bg-[var(--bg-raised)] p-5">
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <span className="font-[family-name:var(--font-mono)] text-xs tracking-wide text-[var(--copper)] uppercase">
                {card.source_type}
              </span>
              <h3 className="text-lg">{card.title}</h3>
            </div>
            <p className="text-[15px] leading-7 text-[#e7dcc4]">{card.excerpt}</p>
            {card.source_url && (
              <a href={card.source_url} className="mt-3 inline-block font-[family-name:var(--font-mono)] text-xs text-[var(--muted)]">
                {card.source_url}
              </a>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
