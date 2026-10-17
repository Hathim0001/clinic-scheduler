import { useEffect, useRef } from "react";
import { formatIST } from "../lib/formatIST";

export interface ConflictedAppointment {
  id: number;
  patient_name: string;
  patient_phone: string;
  start_at_ist: string;
}

interface Props {
  message: string;
  appointments: ConflictedAppointment[];
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Shown when a change to a doctor's hours would leave booked appointments outside the new hours. */
export function ConflictDialog({ message, appointments, busy, onConfirm, onCancel }: Props) {
  const backButton = useRef<HTMLButtonElement>(null);
  useEffect(() => backButton.current?.focus(), []);

  return (
    <div className="overlay">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="conflict-title">
        <h2 id="conflict-title">Booked appointments would be affected</h2>
        <p>{message}</p>
        <ul>
          {appointments.map((appointment) => (
            <li key={appointment.id}>
              {appointment.patient_name}, {appointment.patient_phone}, {formatIST(appointment.start_at_ist)}
            </li>
          ))}
        </ul>
        <p className="muted">
          If you save anyway, these stay booked and are listed as needing attention until someone
          moves or cancels them.
        </p>
        <div className="actions">
          <button type="button" ref={backButton} onClick={onCancel}>
            Go back
          </button>
          <button type="button" className="danger" disabled={busy} onClick={onConfirm}>
            Save anyway
          </button>
        </div>
      </div>
    </div>
  );
}

/** Reads the appointment list out of an AVAILABILITY_CONFLICTS error's details. */
export function conflictedAppointments(details: Record<string, unknown>): ConflictedAppointment[] {
  const list = details.appointments;
  return Array.isArray(list) ? (list as ConflictedAppointment[]) : [];
}
