// Typed API client. All calls go through /api (Vite proxies it in dev,
// nginx would do the same in production-style setups).

export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface Job {
  id: string;
  status: JobStatus;
  summary: string | null;
  sentiment: string | null;
  themes: string[] | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  error: string | null;
}

export interface ChatResponse {
  answer: string;
  cache_status: "HIT" | "MISS";
  prompt_tokens: number;
  completion_tokens: number;
  model_latency_ms: number;
  total_latency_ms: number;
  correlation_id: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function createAnalysis(text: string): Promise<Job> {
  return request<Job>("/analyses", { method: "POST", body: JSON.stringify({ text }) });
}

export function getJob(id: string): Promise<Job> {
  return request<Job>(`/analyses/${id}`);
}

export function sendChat(prompt: string): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}
