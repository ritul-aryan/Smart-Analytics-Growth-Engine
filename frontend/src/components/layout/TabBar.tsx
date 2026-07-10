/**
 * frontend/src/components/layout/TabBar.tsx
 *
 * Horizontal tab navigation — theme-aware via CSS variables.
 * Active tab: violet underline + violet text (accent is same in both themes).
 */

import React from "react";

export interface TabItem {
  label: string;
  badge?: string | number;
  disabled?: boolean;
}

interface TabBarProps {
  tabs: TabItem[];
  activeIndex: number;
  onTabChange: (index: number) => void;
  className?: string;
}

export default function TabBar({
  tabs,
  activeIndex,
  onTabChange,
  className = "",
}: TabBarProps): React.ReactElement {
  return (
    <div
      role="tablist"
      aria-label="Page sections"
      className={[
        "flex gap-0 overflow-x-auto border-b border-[var(--sage-border)] bg-[var(--sage-bg-base)] px-4",
        "scrollbar-none",
        className,
      ].join(" ")}
    >
      {tabs.map((tab, i) => {
        const isActive   = i === activeIndex;
        const isDisabled = tab.disabled === true;

        return (
          <button
            key={tab.label}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-disabled={isDisabled}
            disabled={isDisabled}
            onClick={() => !isDisabled && onTabChange(i)}
            className={[
              "flex shrink-0 items-center gap-1.5 border-b-2 px-4 py-3.5 text-sm font-medium",
              "transition-colors focus:outline-none",
              isActive
                ? "border-[var(--sage-accent)] text-[var(--sage-accent)]"
                : isDisabled
                  ? "cursor-not-allowed border-transparent text-[var(--sage-border)]"
                  : "border-transparent text-[var(--sage-text-muted)] hover:border-[var(--sage-border)] hover:text-[var(--sage-text-primary)]",
            ].join(" ")}
          >
            {tab.label}
            {tab.badge !== undefined && (
              <span
                className={[
                  "rounded-full px-1.5 py-0.5 text-xs font-semibold",
                  isActive
                    ? "bg-[var(--sage-accent-soft)] text-[var(--sage-accent)]"
                    : "bg-[var(--sage-border)] text-[var(--sage-text-muted)]",
                ].join(" ")}
              >
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
