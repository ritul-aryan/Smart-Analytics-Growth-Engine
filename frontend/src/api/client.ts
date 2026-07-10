/**
 * frontend/src/api/client.ts
 *
 * Base HTTP client for all MAE API calls.
 *
 * All API modules import `apiFetch` from here — never use raw `fetch`
 * elsewhere in the codebase.  This ensures:
 *  - Consistent base URL from Vite env vars
 *  - JSON Content-Type on all non-multipart requests
 *  - Typed ApiError thrown on any non-2xx response
 *  - Single place to add auth headers when the auth layer is added
 */

import type { ApiError } from "../types/api";

// ---------------------------------------------------------------------------
// Base URL
// ---------------------------------------------------------------------------

/**
 * Resolved from VITE_API_BASE_URL (set in .env / .env.local).
 * Defaults to the FastAPI dev server address so local dev works with
 * no environment file.
 */
const BASE_URL: string =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ??
  "http://localhost:8000";

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly detail: string;

  constructor(error: ApiError) {
    super(error.detail);
    this.name = "ApiClientError";
    this.status = error.status;
    this.detail = error.detail;
  }
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

/**
 * Thin wrapper around `fetch` that:
 *  1. Prepends BASE_URL
 *  2. Sets Content-Type: application/json for non-FormData bodies
 *  3. Throws ApiClientError for any non-2xx response
 *  4. Returns the parsed JSON body typed as T
 */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path}`;

  const headers = new Headers(init?.headers);

  // Let the browser set Content-Type for FormData (multipart boundary)
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, { ...init, headers });

  if (!response.ok) {
    let detail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Ignore JSON parse errors on error responses
    }
    throw new ApiClientError({ detail, status: response.status });
  }

  // 204 No Content — return empty object
  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Convenience helpers
// ---------------------------------------------------------------------------

export function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "GET" });
}

export function apiPost<T>(
  path: string,
  body: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    body: body instanceof FormData ? body : JSON.stringify(body),
    ...(headers ? { headers } : {}),
  });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE" });
}
