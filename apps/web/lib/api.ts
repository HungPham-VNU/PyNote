/** Typed API client. Generated types arrive in packages/shared-types in M1. */

export type Notebook = {
  id: string;
  title: string;
  org_id: string;
  owner_user_id: string;
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
      "Content-Type": "application/json",
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

export async function listNotebooks(token: string | null): Promise<Notebook[]> {
  return request<Notebook[]>("/api/v1/notebooks", { token });
}

export async function createNotebook(
  token: string | null,
  title: string,
): Promise<Notebook> {
  return request<Notebook>("/api/v1/notebooks", {
    token,
    method: "POST",
    body: JSON.stringify({ title }),
  });
}
