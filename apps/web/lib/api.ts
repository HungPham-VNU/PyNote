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

export type Source = {
  id: string;
  notebook_id: string;
  kind: string;
  status: SourceStatus;
  title: string;
  byte_size: number | null;
  error: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

export async function listNotebooks(token: string | null): Promise<Notebook[]> {
  return request<Notebook[]>("/api/v1/notebooks", { token });
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
