import { useState } from "react";
import { useAppointmentHistory, useCorrect } from "../api/hooks";
import type { Appointment, Status } from "../api/types";
import { formatIST } from "../lib/formatIST";
import { Banner, ErrorBanner, Skeleton } from "./common";

const KIND_TEXT: Record<string, string> = {
  BOOKED: "Booked",
  CANCELLED: "Cancelled",
  LATE_CANCELLED: "Cancelled late",
  RESCHEDULED_FROM: "Moved here from another time",
  COMPLETED: "Marked completed",
  NO_SHOW: "Marked no-show",
  CHECKED_IN: "Patient checked in",
  CORRECTED: "Outcome corrected",
};

const STATUS_TEXT: Record<string, string> = {
  COMPLETED: "completed",
  NO_SHOW: "no-show",
  CANCELLED: "an ordinary cancellation",
};

/** What a final status may be corrected to; the server decides, this only labels the choice. */
const TARGET_OF: Partial<Record<Status, { status: Status; label: string }>> = {
  COMPLETED: { status: "NO_SHOW", label: "No-show (the patient did not attend)" },
  NO_SHOW: { status: "COMPLETED", label: "Completed (the patient was seen)" },
  LATE_CANCELLED: { status: "CANCELLED", label: "Ordinary cancellation (waive the late penalty)" },
};

export function UrgentBadge({ appointment }: { appointment: Appointment }) {
  if (!appointment.urgent_symptoms) return null;
  return (
    <span
      className="status LATE_CANCELLED"
      title="The reason mentions symptoms that may need emergency care"
    >
      {" "}
      Urgent symptoms
    </span>
  );
}

/** Fixes a wrongly recorded outcome. The original stays in the history with the note. */
export function CorrectionForm({ appointment }: { appointment: Appointment }) {
  const correct = useCorrect();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const target = TARGET_OF[appointment.status];
  if (!appointment.allowed_actions.includes("correct") || !target) return null;

  return (
    <div>
      {!open ? (
        <button type="button" onClick={() => setOpen(true)}>
          Correct the outcome…
        </button>
      ) : (
        <fieldset>
          <legend>Correct this outcome</legend>
          <p>
            Change it to <strong>{target.label}</strong>. The original outcome and your note stay in
            the history.
          </p>
          <label>
            Why is it being corrected?
            <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={200} />
          </label>
          <div className="actions">
            <button
              type="button"
              className="primary"
              disabled={note.trim() === "" || correct.isPending}
              onClick={() =>
                correct.mutate(
                  { id: appointment.id, status: target.status, note },
                  { onSuccess: () => setOpen(false) },
                )
              }
            >
              Save the correction
            </button>
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </fieldset>
      )}
      {correct.error && <ErrorBanner error={correct.error} />}
      {correct.isSuccess && <Banner kind="success">Corrected.</Banner>}
    </div>
  );
}

/** The appointment's audit trail, loaded when opened. */
export function History({ appointmentId }: { appointmentId: number }) {
  const [open, setOpen] = useState(false);
  const history = useAppointmentHistory(appointmentId, open);
  return (
    <div>
      <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        {open ? "Hide history" : "History"}
      </button>
      {open && history.isPending && <Skeleton rows={2} />}
      {open && history.error && <ErrorBanner error={history.error} />}
      {open && history.data && (
        <ol aria-label="Appointment history">
          {history.data.map((event) => (
            <li key={event.id}>
              {formatIST(event.at_ist)}: {KIND_TEXT[event.kind] ?? event.kind}
              {event.kind === "CORRECTED" &&
                ` from ${STATUS_TEXT[String(event.detail.from_status)] ?? event.detail.from_status} to ${
                  STATUS_TEXT[String(event.detail.to_status)] ?? event.detail.to_status
                }: ${String(event.detail.note ?? "")}`}
              {(event.kind === "CANCELLED" || event.kind === "LATE_CANCELLED") &&
                ` by ${event.detail.by === "CLINIC" ? "the clinic" : "the patient"}`}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
