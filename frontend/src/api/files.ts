/**
 * frontend/src/api/files.ts
 *
 * Typed wrappers for file upload and download endpoints.
 *
 * uploadFile   — POST /api/upload     (multipart)
 * downloadFile — GET  /api/download/{filename}
 *
 * Note: The primary upload path is via startAnalysis() in analyze.ts.
 * uploadFile() here targets the standalone upload endpoint for future
 * use cases (re-upload, batch mode).
 */

import { apiFetch } from "./client";
import type { UploadResponse } from "../types/api";

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

/**
 * Upload a raw CSV or Excel file.
 * Returns stored_filename which can be passed to startAnalysis separately
 * if the upload/analyze flow is decoupled.
 */
export async function uploadFile(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  return apiFetch<UploadResponse>("/api/upload", {
    method: "POST",
    body: form,
  });
}

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------

/**
 * Download a processed file (clean CSV, engineered CSV, audit log CSV).
 * Triggers a browser download with the correct filename.
 *
 * @param storedFilename  The stored_filename returned from the session
 * @param downloadAs      Optional override for the save-as filename
 */
export async function downloadFile(
  storedFilename: string,
  downloadAs?: string,
): Promise<void> {
  const response = await fetch(
    `${(import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000"}/api/download/${storedFilename}`,
    { method: "GET" },
  );

  if (!response.ok) {
    throw new Error(`Download failed: HTTP ${response.status}`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = downloadAs ?? storedFilename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
