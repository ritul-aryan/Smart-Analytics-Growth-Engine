import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./index.css";

// Apply the persisted theme before first paint to avoid a flash of the
// wrong palette. Dark is the default: "dark" on <html> drives Tailwind
// dark: variants, "light" switches the --sage-* CSS variables.
// After mount, App.tsx owns these classes and syncs them from uiStore.
(() => {
  let theme: unknown = null;
  try {
    const raw = localStorage.getItem("mae-ui-preferences");
    if (raw) theme = (JSON.parse(raw) as { state?: { theme?: unknown } }).state?.theme;
  } catch {
    // Corrupt or unavailable storage: fall through to dark default.
  }
  const isLight = theme === "light";
  document.documentElement.classList.toggle("light", isLight);
  document.documentElement.classList.toggle("dark", !isLight);
})();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 1,
    },
  },
});

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Root element not found");

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
