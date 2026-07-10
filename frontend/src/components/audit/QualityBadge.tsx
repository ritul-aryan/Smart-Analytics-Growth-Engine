/**
 * frontend/src/components/audit/QualityBadge.tsx
 *
 * Colour-coded quality score pill.
 * green ≥ 80 | amber 50–79 | red < 50
 */

interface QualityBadgeProps {
  score: number | null;
  label?: string;
  size?: "sm" | "md";
}

export default function QualityBadge({
  score,
  label = "Quality",
  size = "md",
}: QualityBadgeProps): React.ReactElement {
  const px = size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";

  if (score === null) {
    return (
      <span className={`inline-flex items-center rounded-full bg-[var(--sage-bg-overlay)] font-medium text-[var(--sage-text-muted)] ${px}`}>
        {label}: —
      </span>
    );
  }

  // Colour rule (Section 8.2): green >= 80, amber 50-79, red < 50 — mapped
  // to the prototype tokens good / high / crit.
  const color =
    score >= 80
      ? "bg-[var(--sage-good-soft)] text-[var(--sage-good)]"
      : score >= 50
        ? "bg-[var(--sage-high-soft)] text-[var(--sage-high)]"
        : "bg-[var(--sage-crit-soft)] text-[var(--sage-crit)]";

  return (
    <span className={`inline-flex items-center rounded-full font-semibold ${color} ${px}`}>
      {label}: {score.toFixed(1)}
    </span>
  );
}
