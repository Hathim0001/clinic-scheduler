import type { ReactNode } from "react";

/** Small building blocks shared by the pages: icons, avatars, page titles and figure cards. */

const ICONS = {
  overview: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z",
  calendar:
    "M7 2v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2H7Zm-2 8h14v10H5V10Z",
  plus: "M11 4h2v7h7v2h-7v7h-2v-7H4v-2h7V4Z",
  queue: "M4 6h16v2H4V6Zm0 5h16v2H4v-2Zm0 5h10v2H4v-2Z",
  phone:
    "M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25c1.1.37 2.3.57 3.6.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1l-2.22 2.2Z",
  people:
    "M16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0 2c-2.3 0-7 1.2-7 3.5V19h14v-2.5C15 14.2 10.3 13 8 13Zm8 0c-.3 0-.6 0-.9.05 1.1.8 1.9 1.8 1.9 3.45V19h6v-2.5c0-2.3-4.7-3.5-7-3.5Z",
  message:
    "M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2Zm2 4v2h12V8H6Zm0 4v2h8v-2H6Z",
  chart: "M4 20V10h3v10H4Zm6.5 0V4h3v16h-3ZM17 20v-7h3v7h-3Z",
  doctor:
    "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-8 8c0-3.3 3.6-5 8-5s8 1.7 8 5v1H4v-1Zm7-4v1.5H9.5v1.5H11V20h2v-1.5h1.5V17H13v-1.5h-2Z",
  shield:
    "M12 2 4 5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11V5l-8-3Zm-1 14-3.5-3.5 1.4-1.4L11 13.2l4.1-4.1 1.4 1.4L11 16Z",
  key: "M7 14a4 4 0 1 1 3.9-5H21v3h-2v3h-3v-3h-5.1A4 4 0 0 1 7 14Zm0-5.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z",
  menu: "M3 6h18v2H3V6Zm0 5h18v2H3v-2Zm0 5h18v2H3v-2Z",
  close:
    "m6.4 5 5.6 5.6L17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6l5.6-5.6L5 6.4 6.4 5Z",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v5.2l4 2.4-.8 1.3-4.7-2.8V7H13Z",
  alert: "M12 2 1 21h22L12 2Zm-1 7h2v6h-2V9Zm0 8h2v2h-2v-2Z",
  check: "m9 16.2-3.5-3.5L4 14.1l5 5 11-11-1.4-1.4L9 16.2Z",
  code: "M9.4 16.6 4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4Zm5.2 0 4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4Z",
  arrow: "m12 4-1.4 1.4 5.6 5.6H4v2h12.2l-5.6 5.6L12 20l8-8-8-8Z",
} as const;

export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path d={ICONS[name]} fill="currentColor" />
    </svg>
  );
}

/** The clinic's mark: a cross with rounded ends, softer than a medical-sign plus. */
export function BrandMark({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeWidth="4.2"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

/** Up to two initials, ignoring a leading title such as "Dr." */
export function initialsOf(name: string): string {
  const words = name
    .replace(/^(dr|mr|mrs|ms)\.?\s+/i, "")
    .split(/\s+/)
    .filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => word[0]!.toUpperCase())
    .join("");
}

/** A round badge of initials; the colour follows the name, so one person looks the same everywhere. */
export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" | "lg" }) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) % 360;
  return (
    <span
      className={`avatar avatar-${size}`}
      style={{ ["--hue" as string]: String(hash) }}
      aria-hidden="true"
    >
      {initialsOf(name)}
    </span>
  );
}

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

/** The title of a page, one line of what it is for, and the buttons that act on the whole page. */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "brand" | "warn" | "danger" | "ok";
  icon?: IconName;
}

/** One figure with its label, for the strips at the top of a page. */
export function StatCard({ label, value, hint, tone = "default", icon }: StatCardProps) {
  return (
    <div className={`stat-card tone-${tone}`}>
      {icon && (
        <span className="stat-icon">
          <Icon name={icon} size={18} />
        </span>
      )}
      <div className="stat-body">
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        {hint && <div className="stat-hint">{hint}</div>}
      </div>
    </div>
  );
}

/** A bar showing how much of something is used. The figures are written beside it, never only drawn. */
export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const percent = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div
      className="meter"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
    >
      <div className="meter-fill" style={{ width: `${percent}%` }} />
    </div>
  );
}
