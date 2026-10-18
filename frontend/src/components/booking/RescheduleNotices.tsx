import { ApiError } from "../../api/client";
import { Banner } from "../common";

export type Mover = "PATIENT" | "CLINIC";

/** Who is moving the appointment: only a patient's late move counts against them. */
export function MoverFieldset({
  mover,
  onChange,
}: {
  mover: Mover;
  onChange: (mover: Mover) => void;
}) {
  return (
    <fieldset>
      <legend>Who is moving it?</legend>
      <label className="check">
        <input
          type="radio"
          name="mover"
          checked={mover === "PATIENT"}
          onChange={() => onChange("PATIENT")}
        />
        The patient (a move inside 2 hours is recorded as a late cancellation)
      </label>
      <label className="check">
        <input
          type="radio"
          name="mover"
          checked={mover === "CLINIC"}
          onChange={() => onChange("CLINIC")}
        />
        The clinic (never counts against the patient)
      </label>
    </fieldset>
  );
}

/** True when the server is asking before it records a late cancellation. */
export const isLateMoveQuestion = (error: unknown): error is ApiError =>
  error instanceof ApiError && error.code === "LATE_RESCHEDULE_NEEDS_CONFIRMATION";

/** The server's question about a late move, with the two ways to answer it. */
export function LateMoveQuestion({
  error,
  pending,
  onConfirm,
  onClinicInstead,
}: {
  error: ApiError;
  pending: boolean;
  onConfirm: () => void;
  onClinicInstead: () => void;
}) {
  return (
    <Banner kind="warn">
      <p>{error.message}</p>
      <div className="actions">
        <button type="button" onClick={onConfirm} disabled={pending}>
          Move it anyway (late cancellation)
        </button>
        <button type="button" onClick={onClinicInstead}>
          Have the clinic make the move
        </button>
      </div>
    </Banner>
  );
}
