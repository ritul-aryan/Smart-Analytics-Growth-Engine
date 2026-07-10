/**
 * frontend/src/components/upload/FileDropZone.tsx
 *
 * Drag-and-drop file upload area.
 *
 * Accepts CSV, XLSX, XLS files up to the configured size limit.
 * Supports both drag-and-drop and click-to-browse.
 * Shows file name + size after selection; clears on X button.
 */

import { useCallback, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FileDropZoneProps {
  onFileSelected: (file: File) => void;
  onFileCleared: () => void;
  selectedFile: File | null;
  disabled?: boolean;
}

const ACCEPTED_EXTENSIONS = [".csv", ".xlsx", ".xls"];
const ACCEPTED_MIME = [
  "text/csv",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
];
const MAX_SIZE_MB = 50;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isValidFile(file: File): string | null {
  const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
  if (!ACCEPTED_EXTENSIONS.includes(ext)) {
    return `Unsupported file type "${ext}". Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`;
  }
  if (file.size > MAX_SIZE_BYTES) {
    return `File too large (${formatBytes(file.size)}). Maximum: ${MAX_SIZE_MB} MB`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FileDropZone({
  onFileSelected,
  onFileCleared,
  selectedFile,
  disabled = false,
}: FileDropZoneProps): React.ReactElement {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File) => {
      const validationError = isValidFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      setError(null);
      onFileSelected(file);
    },
    [onFileSelected],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [disabled, handleFile],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      // Reset input so same file can be re-selected
      e.target.value = "";
    },
    [handleFile],
  );

  // State styling mirrors the SAGE.html prototype drop zone:
  //   idle      — dashed border2 on card surface
  //   drag-over — accent border + accent-soft fill
  //   selected  — accent-tinted border on card surface
  //   error     — critical border on card surface
  const borderClass = dragOver
    ? "border-[var(--sage-accent)] bg-[var(--sage-accent-soft)]"
    : selectedFile
      ? "border-[var(--sage-accent-border)] bg-[var(--sage-bg-elevated)]"
      : error
        ? "border-[var(--sage-crit)] bg-[var(--sage-bg-elevated)]"
        : "border-[var(--sage-border-strong)] bg-[var(--sage-bg-elevated)] hover:border-[var(--sage-accent-border)]";

  return (
    <div className="w-full">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="File drop zone — drag a CSV or Excel file here, or click to browse"
        className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-colors cursor-pointer ${borderClass} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") inputRef.current?.click(); }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={[...ACCEPTED_EXTENSIONS, ...ACCEPTED_MIME].join(",")}
          className="sr-only"
          onChange={handleInputChange}
          disabled={disabled}
          aria-hidden="true"
        />

        {selectedFile ? (
          <div className="flex flex-col items-center gap-2 text-center">
            <span className="text-3xl">📄</span>
            <p className="font-semibold text-[var(--sage-text-primary)]">{selectedFile.name}</p>
            <p className="text-sm text-[var(--sage-text-muted)]">{formatBytes(selectedFile.size)}</p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setError(null); onFileCleared(); }}
              className="mt-1 rounded-full bg-[var(--sage-bg-overlay)] px-3 py-1 text-xs text-[var(--sage-text-muted)] hover:text-[var(--sage-crit)] transition-colors"
              aria-label="Remove selected file"
            >
              ✕ Remove
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-center">
            <span className="text-4xl">☁️</span>
            <p className="font-semibold text-[var(--sage-text-primary)]">
              Drop your file here, or{" "}
              <span className="text-[var(--sage-accent)] underline">browse</span>
            </p>
            <p className="text-sm text-[var(--sage-text-dim)]">
              CSV, XLSX, XLS · max {MAX_SIZE_MB} MB
            </p>
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-2 text-sm text-[var(--sage-crit)]">
          {error}
        </p>
      )}
    </div>
  );
}
