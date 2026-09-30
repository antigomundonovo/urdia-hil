/** API client — every call is workspace/profile-scoped server-side. */

export const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export interface Profile {
  id: string;
  workspace_id: string;
  key: string;
  name: string;
  language: string | null;
  status: string | null;
}

export interface Opportunity {
  id: string;
  title: string;
  description: string | null;
  why_now: string | null;
  why_profile: string | null;
  decision: string | null;
  decision_reason: string | null;
  priority: string | null;
  state: string;
  created_at: string;
}

export interface QcResult {
  status: string;
  gates: Record<string, string>;
  blocking_issues: string[];
  warnings: string[];
}

export interface Source {
  id: string;
  url: string;
  source_type: string;
  title: string | null;
  publisher: string | null;
  status: string;
}

export interface CommentItem {
  id: string;
  intent: string | null;
  qualified_signal: string | null;
  text: string | null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

export const qs = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v && search.set(k, v));
  return search.toString();
};
