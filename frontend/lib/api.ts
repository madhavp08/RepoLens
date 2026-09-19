const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Job = {
  id: string;
  repository_id: string;
  wave: number;
  status: string;
  progress: Record<string, unknown>;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type Repository = {
  id: string;
  owner: string;
  name: string;
  github_url: string;
  default_branch: string | null;
  description: string | null;
  stars: number;
  last_synced_at: string | null;
  document_count: number;
  chunk_count: number;
};

export type ImportResponse = {
  repository: Repository;
  job: Job;
  already_indexed: boolean;
};

export type RepositoryDetail = {
  repository: Repository;
  jobs: Job[];
};

export type SourceCard = {
  document_id: string;
  chunk_id: string;
  source_type: string;
  title: string;
  source_url: string | null;
  excerpt: string;
  rank: number;
  extra: Record<string, unknown>;
};

export type SearchResponse = {
  query: string;
  repository_id: string;
  coverage: {
    document_count: number;
    waves: { wave: number; status: string; progress: Record<string, unknown> }[];
  };
  results: SourceCard[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function importRepository(url: string, force = false) {
  return request<ImportResponse>("/v1/repositories", {
    method: "POST",
    body: JSON.stringify({ url, force }),
  });
}

export function getRepository(id: string) {
  return request<RepositoryDetail>(`/v1/repositories/${id}`);
}

export function getJob(id: string) {
  return request<Job>(`/v1/jobs/${id}`);
}

export function searchRepository(id: string, query: string) {
  return request<SearchResponse>(`/v1/repositories/${id}/search`, {
    method: "POST",
    body: JSON.stringify({ query, limit: 20 }),
  });
}
