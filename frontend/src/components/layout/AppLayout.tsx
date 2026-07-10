/**
 * frontend/src/components/layout/AppLayout.tsx
 *
 * Persistent shell shared by every route.
 * Renders the Sidebar on the left and the current route's page content
 * on the right via React Router's Outlet.
 *
 * Each child page only needs to render its own content column (TopBar +
 * main area) -- the outer flex container and Sidebar live here so they
 * are never unmounted during client-side navigation.
 */

import React from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function AppLayout(): React.ReactElement {
  return (
    <div className="flex h-screen overflow-hidden bg-[var(--sage-bg-base)]">
      <Sidebar />
      <Outlet />
    </div>
  );
}
