import type { ReactNode } from "react";
import { describeError } from "../lib/errors";
import type { Status } from "../api/types";

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton" />
      ))}
    </div>
  );
}

interface ErrorBannerProps {
  error: unknown;
  doctorName?: string;
  onRetry?: () => void;
}

/** One place that turns an API failure into words. Never shows raw JSON. */
export function ErrorBanner({ error, doctorName, onRetry }: ErrorBannerProps) {
  const friendly = describeError(error, { doctorName });
  return (
    <div className="banner error" role="alert">
      <strong>{friendly.message}</strong>
      {friendly.lines.length > 0 && (
        <ul>
          {friendly.lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {friendly.requestId && (
        <div className="request-id">
          Request id <code>{friendly.requestId}</code>
        </div>
      )}
      {friendly.retryable && onRetry && (
        <p>
          <button type="button" onClick={onRetry}>
            Try again
          </button>
        </p>
      )}
    </div>
  );
}

const STATUS_LABEL: Record<Status, string> = {
  BOOKED: "Booked",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  LATE_CANCELLED: "Cancelled late",
  NO_SHOW: "No-show",
};

/** Status as text, so it is never colour alone. */
export function StatusBadge({ status }: { status: Status }) {
  return <span className={`status ${status}`}>{STATUS_LABEL[status]}</span>;
}

export function Banner({
  kind,
  children,
}: {
  kind: "info" | "warn" | "success" | "error";
  children: ReactNode;
}) {
  return (
    <div className={`banner ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}
