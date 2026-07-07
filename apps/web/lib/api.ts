/** Typed API client. Mirrors apps/api routes; generated types arrive in M2+. */

export type Notebook = {
  id: string;
  title: string;
  org_id: string;
  owner_user_id: string;
};

export type SourceStatus =
  | "pending"
  | "uploading"
  | "parsing"
  | "parsed"
  | "embedding"
  | "ready"
  | "failed";

export type SourceMeta = {
  abstract?: string;
  key_entities?: string[];
  suggested_questions?: string[];
};

export type Source = {
  id: string;
  notebook_id: string;
  kind: string;
  status: SourceStatus;
  title: string;
  byte_size: number | null;
  error: string | null;
  meta?: SourceMeta;
};

const API_BASE = typeof window === "undefined" ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") : "";

async function request<T>(
  path: string,
  init: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, headers, ...rest } = init;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Notebooks -------------------------------------------------------------

export async function listNotebooks(
  token: string | null,
  query?: string,
): Promise<Notebook[]> {
  const qs = query ? `?q=${encodeURIComponent(query)}` : "";
  return request<Notebook[]>(`/api/v1/notebooks${qs}`, { token });
}

export async function getNotebook(
  token: string | null,
  id: string,
): Promise<Notebook> {
  return request<Notebook>(`/api/v1/notebooks/${id}`, { token });
}

export async function createNotebook(
  token: string | null,
  title: string,
): Promise<Notebook> {
  return request<Notebook>("/api/v1/notebooks", {
    token,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function updateNotebook(
  token: string | null,
  id: string,
  title: string,
): Promise<Notebook> {
  return request<Notebook>(`/api/v1/notebooks/${id}`, {
    token,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteNotebook(
  token: string | null,
  id: string,
): Promise<void> {
  return request<void>(`/api/v1/notebooks/${id}`, {
    token,
    method: "DELETE",
  });
}

// ---- Sources ---------------------------------------------------------------

export async function listSources(
  token: string | null,
  notebookId: string,
): Promise<Source[]> {
  return request<Source[]>(`/api/v1/notebooks/${notebookId}/sources`, { token });
}

export async function uploadSource(
  token: string | null,
  notebookId: string,
  file: File,
): Promise<Source> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<Source>(
    `/api/v1/notebooks/${notebookId}/sources/upload`,
    { token, method: "POST", body: form },
  );
}

export async function deleteSource(
  token: string | null,
  sourceId: string,
): Promise<void> {
  return request<void>(`/api/v1/sources/${sourceId}`, {
    token,
    method: "DELETE",
  });
}

// ---- Summary -------------------------------------------------------------

export type NotebookSummary = {
  headline: string;
  key_points: string[];
  detailed_summary: string;
  generated_at: string;
  model_used: string | null;
};

export async function getNotebookSummary(
  token: string | null,
  notebookId: string,
): Promise<NotebookSummary | null> {
  const res = await fetch(`${API_BASE}/api/v1/notebooks/${notebookId}/summary`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`summary HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function generateNotebookSummary(
  token: string | null,
  notebookId: string,
): Promise<NotebookSummary> {
  return request<NotebookSummary>(`/api/v1/notebooks/${notebookId}/summary`, {
    token,
    method: "POST",
  });
}

// ---- Mind map (M12) --------------------------------------------------------

export type MindMapCitation = {
  source_id: string;
  source_part_id: string;
  source_title: string | null;
  page: number | null;
  quote: string;
  roundtrip_ok: boolean;
};

export type MindMapNode = {
  id: string;
  label: string;
  kind: string;
  citations: MindMapCitation[];
};

export type MindMapEdge = {
  from: string;
  to: string;
  label: string;
  citations: MindMapCitation[];
};

export type MindMapStatus = "generating" | "ready" | "failed";

export type MindMap = {
  status: MindMapStatus;
  generated_at: string | null;
  error: string | null;
  nodes: MindMapNode[];
  edges: MindMapEdge[];
};

export async function getMindMap(
  token: string | null,
  notebookId: string,
): Promise<MindMap | null> {
  const res = await fetch(`${API_BASE}/api/v1/notebooks/${notebookId}/mind-map`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`mind-map HTTP ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function generateMindMap(
  token: string | null,
  notebookId: string,
): Promise<MindMap> {
  return request<MindMap>(`/api/v1/notebooks/${notebookId}/mind-map`, {
    token,
    method: "POST",
  });
}
