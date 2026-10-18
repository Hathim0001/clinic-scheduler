import { useState } from "react";
import { useNavigate } from "react-router";
import { useCancel, useCheckIn, useComplete, useNoShow } from "../api/hooks";
import type { Action, Appointment, CancelledBy } from "../api/types";
import { whyDisabled } from "../lib/errors";
import { Banner, ErrorBanner } from "./common";

/**
 * The four things that can be done to an appointment. Which ones are on comes from the server's
 * `allowed_actions`; the page never works that out. A switched-off button says why.
 */
export function ActionButtons({ appointment }: { appointment: Appointment }) {
  const navigate = useNavigate();
  const cancel = useCancel();
  const complete = useComplete();
  const noShow = useNoShow();
  const checkIn = useCheckIn();
  const [confirming, setConfirming] = useState(false);
  const [by, setBy] = useState<CancelledBy>("PATIENT");

  const allowed = new Set<Action>(appointment.allowed_actions);
  const error = cancel.error ?? complete.error ?? noShow.error ?? checkIn.error;
  const busy = cancel.isPending || complete.isPending || noShow.isPending || checkIn.isPending;

  // Only what can be done now is shown. A row of switched-off buttons that repeat on every line
  // hides the one that matters, so what is not available is explained once, in words.
  const unavailable = (["complete", "no-show", "reschedule", "cancel"] as const).filter(
    (action) => !allowed.has(action),
  );
  const note =
    unavailable.length > 0 ? whyDisabled(unavailable[0] ?? "cancel", appointment.status) : null;

  return (
    <div>
      <div className="actions">
        {allowed.has("check-in") && (
          <button type="button" disabled={busy} onClick={() => checkIn.mutate(appointment.id)}>
            Check in
          </button>
        )}
        {allowed.has("complete") && (
          <button type="button" disabled={busy} onClick={() => complete.mutate(appointment.id)}>
            Complete
          </button>
        )}
        {allowed.has("no-show") && (
          <button type="button" disabled={busy} onClick={() => noShow.mutate(appointment.id)}>
            No-show
          </button>
        )}
        {allowed.has("reschedule") && (
          <button
            type="button"
            disabled={busy}
            onClick={() => navigate(`/book?reschedule=${appointment.id}`)}
          >
            Reschedule
          </button>
        )}
        {allowed.has("cancel") && (
          <button
            type="button"
            className="danger"
            disabled={busy}
            onClick={() => setConfirming(true)}
          >
            Cancel…
          </button>
        )}
      </div>
      {note && <p className="muted action-note">{note}</p>}

      {confirming && (
        <fieldset>
          <legend>Cancel this appointment as</legend>
          <label className="check">
            <input
              type="radio"
              name={`by-${appointment.id}`}
              checked={by === "PATIENT"}
              onChange={() => setBy("PATIENT")}
            />
            The patient (a cancellation close to the start is recorded as late)
          </label>
          <label className="check">
            <input
              type="radio"
              name={`by-${appointment.id}`}
              checked={by === "CLINIC"}
              onChange={() => setBy("CLINIC")}
            />
            The clinic (never counts against the patient)
          </label>
          <div className="actions">
            <button
              type="button"
              className="danger"
              disabled={cancel.isPending}
              onClick={() =>
                cancel.mutate({ id: appointment.id, by }, { onSuccess: () => setConfirming(false) })
              }
            >
              Confirm cancellation
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Keep it
            </button>
          </div>
        </fieldset>
      )}

      {cancel.data && (
        <Banner kind={cancel.data.late ? "warn" : "success"}>
          {cancel.data.late
            ? "Cancelled late: this counts toward the patient's deposit flag."
            : "Cancelled."}
        </Banner>
      )}
      {error && <ErrorBanner error={error} doctorName={appointment.doctor_name} />}
    </div>
  );
}
