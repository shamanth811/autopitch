import type { Job, JobSummary, Report, Rubric } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

const KEY_STORE = "autopitch.apiKey";
const OWNER_STORE = "autopitch.owner";
let memoryOwner: string | undefined;

/** Anonymous per-browser id. It scopes saved reports to this browser; it is not a login. */
export function ownerId(): string {
  try {
    let id = localStorage.getItem(OWNER_STORE);
    if (!id) {
      id = crypto.randomUUID().replace(/-/g, "");
      localStorage.setItem(OWNER_STORE, id);
    }
    return id;
  } catch {
    memoryOwner ??= crypto.randomUUID().replace(/-/g, "");
    return memoryOwner;
  }
}

export function getApiKey(): string {
  try {
    return sessionStorage.getItem(KEY_STORE) ?? "";
  } catch {
    return "";
  }
}

export function setApiKey(key: string): void {
  try {
    sessionStorage.setItem(KEY_STORE, key);
  } catch {
    /* storage unavailable; the key stays in the form only */
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { "X-Owner-Id": ownerId() };
  const key = getApiKey();
  if (key) h["X-API-Key"] = key;
  return h;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const j = await res.json();
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* non-JSON body (the 500 handler returns plain text) */
  }
  return `Request failed (${res.status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: { ...headers(), ...init.headers } });
  } catch (e) {
    if (init.signal?.aborted) throw e;
    throw new ApiError(0, "Could not reach the AutoPitch server.");
  }
  if (!res.ok) {
    const n = Number(res.headers.get("Retry-After"));
    throw new ApiError(res.status, await errorMessage(res), n > 0 ? n : undefined);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export async function createJob(file: File): Promise<{ id: string }> {
  const body = new FormData();
  body.append("file", file);
  return request("/v1/jobs", { method: "POST", body });
}

export const getJob = (id: string, signal?: AbortSignal) =>
  request<Job>(`/v1/jobs/${encodeURIComponent(id)}`, { signal });

export const listJobs = () => request<JobSummary[]>("/v1/jobs");

export const deleteJob = (id: string) =>
  request<void>(`/v1/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });

export const getRubric = () => request<Rubric>("/v1/rubric");

export type { Report };
