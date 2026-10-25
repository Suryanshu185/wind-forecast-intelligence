import type { ApiErrorBody } from "./types";

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Array<{ field?: string | null; message: string }>;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string, details: ApiClientError["details"] = []) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
    // Network failures (status 0), 429 and 5xx may succeed on retry; 4xx validation errors will not.
    this.retryable = status === 0 || status === 429 || status >= 500;
  }
}

const BASE = (import.meta.env?.VITE_API_BASE_URL as string | undefined) ?? "";

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { headers: { Accept: "application/json" }, signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiClientError(0, "NETWORK", "Could not reach the analysis service. Check your connection and retry.");
  }
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await res.json()) as ApiErrorBody;
    } catch {
      /* not JSON: e.g. a proxy error page or a cold-starting host */
    }
    if (body?.error) {
      throw new ApiClientError(res.status, body.error.code, body.error.message, body.error.details ?? []);
    }
    throw new ApiClientError(res.status, "HTTP_ERROR", `The service responded with HTTP ${res.status}.`);
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiClientError(res.status, "BAD_RESPONSE", "The service returned an unreadable response.");
  }
}
