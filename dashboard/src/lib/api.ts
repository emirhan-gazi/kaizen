/** API client for Kaizen backend. */

const API_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_CT_API_URL ?? "http://localhost:8000")
    : (process.env.CT_API_URL ?? "http://api:8000");

function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ct_api_key");
}

export function setApiKey(key: string) {
  localStorage.setItem("ct_api_key", key);
}

export function clearApiKey() {
  localStorage.removeItem("ct_api_key");
}

export function hasApiKey(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("ct_api_key");
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const apiKey = getApiKey();
  if (!apiKey) {
    throw new Error("Not authenticated");
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      ...init?.headers,
    },
  });

  if (res.status === 401) {
    clearApiKey();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new Error("Invalid API key");
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Validate an API key against the health/tasks endpoint. */
export async function validateApiKey(key: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/tasks/?limit=1`, {
      headers: {
        "X-API-Key": key,
        "Content-Type": "application/json",
      },
    });
    return res.ok;
  } catch {
    return false;
  }
}

// --- Type definitions matching API schemas ---

export interface TaskSummary {
  id: string;
  name: string;
  description: string | null;
  schema_json: Record<string, unknown> | null;
  feedback_threshold: number;
  feedback_count: number;
  last_optimization: string | null;
  active_prompt_score: number | null;
  threshold_progress: string;
  created_at: string;
  mode?: string;
  git_repo?: string | null;
  git_provider?: string | null;
}

export interface JobResponse {
  id: string;
  task_id: string;
  prompt_version_id: string | null;
  status: string;
  triggered_by: string | null;
  feedback_count: number | null;
  pr_url: string | null;
  error_message: string | null;
  job_metadata: Record<string, unknown> | null;
  progress_step: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface PromptResponse {
  id: string;
  task_id: string;
  version_number: number;
  prompt_text: string | null;
  original_prompt: string | null;
  eval_score: number | null;
  judge_score: number | null;
  status: string;
  optimizer: string | null;
  dspy_version: string | null;
  created_at: string;
}

// --- API methods ---

export function fetchTasks(cursor?: string): Promise<TaskSummary[]> {
  const params = cursor ? `?cursor=${cursor}` : "";
  return apiFetch<TaskSummary[]>(`/api/v1/tasks/${params}`);
}

export function fetchTask(taskId: string): Promise<TaskSummary> {
  return apiFetch<TaskSummary>(`/api/v1/tasks/${taskId}`);
}

export function fetchJobs(taskId?: string, limit = 50): Promise<JobResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (taskId) params.set("task_id", taskId);
  return apiFetch<JobResponse[]>(`/api/v1/jobs/?${params}`);
}

export function fetchJob(jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/v1/jobs/${jobId}`);
}

export function fetchPromptVersions(taskId: string): Promise<PromptResponse[]> {
  return apiFetch<PromptResponse[]>(`/api/v1/prompts/${taskId}/versions`);
}

export function retryPr(jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/v1/jobs/${jobId}/retry-pr`, {
    method: "POST",
  });
}

export function createPrFromPreview(jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/v1/jobs/${jobId}/create-pr`, {
    method: "POST",
  });
}

export function rejectOptimization(jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/v1/jobs/${jobId}/reject`, {
    method: "POST",
  });
}

export interface OptimizeResponse {
  job: JobResponse;
  cost_estimate: {
    estimated_cost_usd: number;
    estimated_llm_calls: number;
    train_size: number;
    val_size: number;
    max_trials: number;
    teacher_model: string;
    judge_model: string;
  };
  budget_warning: string | null;
}

export function triggerOptimization(taskId: string): Promise<OptimizeResponse> {
  return apiFetch<OptimizeResponse>(`/api/v1/optimize/${taskId}`, {
    method: "POST",
  });
}

// --- API Key management ---

export async function checkHasKeys(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/keys/status`);
    if (!res.ok) return true; // assume keys exist on error
    const data = await res.json();
    return data.has_keys;
  } catch {
    return true;
  }
}

export async function bootstrapKey(
  label?: string,
): Promise<{ key: string; id: string }> {
  const res = await fetch(`${API_BASE}/api/v1/keys/bootstrap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: label || "default" }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Bootstrap failed: ${body}`);
  }
  return res.json();
}

export interface ApiKeyInfo {
  id: string;
  label: string | null;
  created_at: string;
  revoked_at: string | null;
}

export function fetchKeys(): Promise<ApiKeyInfo[]> {
  return apiFetch<ApiKeyInfo[]>("/api/v1/keys/");
}

export function createKey(
  label?: string,
): Promise<{ id: string; key: string; label: string | null; created_at: string }> {
  return apiFetch("/api/v1/keys/", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export function revokeKey(keyId: string): Promise<void> {
  return apiFetch(`/api/v1/keys/${keyId}`, { method: "DELETE" }).then(
    () => {},
  );
}

export async function deleteTask(taskId: string): Promise<void> {
  const apiKey = getApiKey();
  if (!apiKey) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/v1/tasks/${taskId}`, {
    method: "DELETE",
    headers: { "X-API-Key": apiKey },
  });
  if (res.status === 401) {
    clearApiKey();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Invalid API key");
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
}
