import { useState } from "react";
import { useNavigate } from "react-router";
import { useCancel, useComplete, useNoShow } from "../api/hooks";
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
  const [confirming, setConfirming] = useState(false);
  const [by, setBy] = useState<CancelledBy>("PATIENT");

  const allowed = new Set<Action>(appointment.allowed_actions);
  const hint = (action: Action) =>
    allowed.has(action) ? undefined : whyDisabled(action, appointment.status);
  const error = cancel.error ?? complete.error ?? noShow.error;
  const busy = cancel.isPending || complete.isPending || noShow.isPending;

  return (
    <div>
      <div className="actions">
        <button
          type="button"
          disabled={!allowed.has("complete") || busy}
          title={hint("complete")}
          onClick={() => complete.mutate(appointment.id)}
        >
          Complete
        </button>
        <button
          type="button"
          disabled={!allowed.has("no-show") || busy}
          title={hint("no-show")}
          onClick={() => noShow.mutate(appointment.id)}
        >
          No-show
        </button>
        <button
          type="button"
          disabled={!allowed.has("reschedule") || busy}
          title={hint("reschedule")}
          onClick={() => navigate(`/book?reschedule=${appointment.id}`)}
        >
          Reschedule
        </button>
        <button
          type="button"
          className="danger"
          disabled={!allowed.has("cancel") || busy}
          title={hint("cancel")}
          onClick={() => setConfirming(true)}
        >
          Cancel…
        </button>
      </div>

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
