/**
 * frontend/src/App.tsx
 *
 * Root router + global error boundary + theme sync.
 * Theme: dark is the CSS :root default; adding "light" class to <html>
 * activates the light palette defined in index.css.
 */

import React, { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useUiStore } from "./store/uiStore";
import AppLayout from "./components/layout/AppLayout";

const UploadPage    = lazy(() => import("./pages/UploadPage"));
const AuditPage     = lazy(() => import("./pages/AuditPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const SettingsPage  = lazy(() => import("./pages/SettingsPage"));

// ---------------------------------------------------------------------------
// Error boundary
// ---------------------------------------------------------------------------

interface EBState { hasError: boolean; message: string }

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, EBState> {
  state: EBState = { hasError: false, message: "" };

  static getDerivedStateFromError(err: unknown): EBState {
    const message = err instanceof Error ? err.message : String(err);
    return { hasError: true, message };
  }

  render(): React.ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[var(--sage-bg-base)] px-6 text-center">
          <p className="text-lg font-semibold text-[var(--sage-crit)]">Something went wrong</p>
          <p className="max-w-md text-xs text-[var(--sage-text-muted)]">{this.state.message}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg bg-[var(--sage-accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function PageSpinner(): React.ReactElement {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--sage-bg-base)]">
      <span className="text-sm text-[var(--sage-text-muted)]">Loading...</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root: theme class wiring + router
// ---------------------------------------------------------------------------

export default function App(): React.ReactElement {
  const theme = useUiStore((s) => s.theme);

  // Single owner of the theme classes on <html> (main.tsx pre-paints them once).
  // "light" switches the --sage-* CSS variables (dark is the :root default);
  // "dark" drives Tailwind dark: variants (darkMode: "class").
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("light", theme === "light");
    root.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Suspense fallback={<PageSpinner />}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/"                     element={<UploadPage />} />
              <Route path="/audit/:sessionId"     element={<AuditPage />} />
              <Route path="/dashboard/:sessionId" element={<DashboardPage />} />
              <Route path="/settings"             element={<SettingsPage />} />
              <Route path="*"                     element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
