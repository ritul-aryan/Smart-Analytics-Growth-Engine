/**
 * frontend/src/api/sessions.ts
 *
 * Typed wrappers for session read endpoints.
 *
 * getSession  — GET /api/session/{id}   (full detail with anomalies + charts)
 * getSessions — GET /api/sessions       (paginated session list)
 */

import { apiGet, apiDelete } from "./client";
import type { SessionDetailResponse, SessionListResponse } from "../types/api";

// ---------------------------------------------------------------------------
// Single session (used by polling loop + AuditPage + DashboardPage)
// ---------------------------------------------------------------------------

/**
 * Fetch full session detail including anomalies, audit log, charts,
 * and EDA narrative.  Returns null if the session is not found (404).
 */
export async function getSession(
  sessionId: string,
): Promise<SessionDetailResponse | null> {
  try {
    return await apiGet<SessionDetailResponse>(`/api/session/${sessionId}`);
  } catch (err) {
    // Treat 404 as null so callers don't need to catch
    if (err instanceof Error && "status" in err && (err as { status: number }).status === 404) {
      return null;
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Session list (used by Sidebar session history)
// ---------------------------------------------------------------------------

/**
 * Fetch a paginated list of all sessions, newest first.
 *
 * @param limit  Max sessions to return (default 20)
 * @param offset Pagination offset (default 0)
 */
export async function getSessions(
  limit = 20,
  offset = 0,
): Promise<SessionListResponse> {
  return apiGet<SessionListResponse>(
    `/api/sessions?limit=${limit}&offset=${offset}`,
  );
}

// ---------------------------------------------------------------------------
// Delete session
// ---------------------------------------------------------------------------

/**
 * Hard-delete a session and all its child data (anomalies, charts, audit
 * log, files, chat messages).  The server responds with 204 No Content.
 */
export async function deleteSession(sessionId: string): Promise<void> {
  await apiDelete<void>(`/api/sessions/${sessionId}`);
}
