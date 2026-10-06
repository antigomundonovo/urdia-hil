/** API client — every call is workspace/profile-scoped server-side. */

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface Profile {
  id: string;
  workspace_id: string;
  key: string;
  name: string;
  language: string | null;
  status: string | null;
}

export interface AuthContext {
  user: { id: string; email: string; name: string | null };
  workspaces: {
    id: string;
    name: string;
    profile: Profile | null;
  }[];
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
  content_package_id?: string | null;
  claims?: { id: string; text: string; status: string }[];
}

export interface ContentPackage {
  id: string;
  workspace_id: string;
  opportunity_id: string;
  canonical_content_id: string;
  format: string;
  opportunity_state: string;
  drafts: {
    id: string;
    title: string | null;
    caption: string | null;
    status: string;
    claim_ids_used: string[];
  }[];
  latest_qc: {
    status: string;
    gates: Record<string, string>;
    is_current: boolean;
  } | null;
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

export interface Job {
  id: string;
  workspace_id: string;
  profile_id: string | null;
  job_type: string;
  status: string;
  attempt: number | null;
  max_attempts: number | null;
  checkpoint: { completed_steps?: string[]; next_step?: string | null } | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CommentItem {
  id: string;
  intent: string | null;
  qualified_signal: string | null;
  text: string | null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const isForm = options?.body instanceof FormData;
  const resp = await fetch(`${API_URL}${path}`, {
    headers: isForm ? undefined : { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`${resp.status}: ${detail}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  download: async (path: string, filename: string) => {
    const response = await fetch(`${API_URL}${path}`, { credentials: "include" });
    if (!response.ok) {
      throw new Error(`${response.status}: ${await response.text()}`);
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

export const qs = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v && search.set(k, v));
  return search.toString();
};
