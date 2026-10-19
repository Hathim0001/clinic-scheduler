import { useEffect, useState } from "react";
import { usePolicy, useUndoCancel } from "../api/hooks";
import { forgetCancel, useLastCancel } from "../lib/lastCancel";
import { formatDayIST, formatTimeIST } from "../lib/formatIST";
import { ErrorBanner } from "./common";

// The bar goes a minute sooner than the server's undo window, so it never offers a dead button.
const showForMs = (undoMinutes: number) => Math.max(0, undoMinutes - 1) * 60 * 1000;

/**
 * Offered right after a cancellation, wherever the person has gone since: one press takes it back.
 * The server decides whether that is still possible (the slot may have been taken meanwhile).
 */
export function UndoCancel() {
  const last = useLastCancel();
  const undo = useUndoCancel();
  const undoMinutes = usePolicy().data?.undo_minutes ?? 10;
  const [restored, setRestored] = useState<string | null>(null);

  useEffect(() => {
    if (!last) return;
    const left = showForMs(undoMinutes) - (Date.now() - last.at);
    if (left <= 0) {
      forgetCancel();
      return;
    }
    const timer = window.setTimeout(forgetCancel, left);
    return () => window.clearTimeout(timer);
  }, [last, undoMinutes]);

  if (!last && !restored && !undo.error) return null;
  const appointment = last?.appointment;
  const when = appointment
    ? `${formatDayIST(appointment.start_at_ist)} ${formatTimeIST(appointment.start_at_ist)}`
    : "";

  return (
    <div className="undo-bar" role="status">
      {restored && <p>{restored}</p>}
      {appointment && !restored && (
        <>
          <p>
            Cancelled {appointment.patient_name}, {when}.
          </p>
          <button
            type="button"
            disabled={undo.isPending}
            onClick={() =>
              undo.mutate(
                { id: appointment.id, etag: appointment.etag },
                {
                  onSuccess: (done) => {
                    setRestored(`Restored ${done.patient_name}, ${when}.`);
                    forgetCancel();
                    window.setTimeout(() => setRestored(null), 6000);
                  },
                },
              )
            }
          >
            {undo.isPending ? "Undoing…" : "Undo"}
          </button>
          <button type="button" className="link" onClick={forgetCancel}>
            Dismiss
          </button>
        </>
      )}
      {undo.error && <ErrorBanner error={undo.error} />}
    </div>
  );
}
