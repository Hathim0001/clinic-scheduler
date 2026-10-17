import { Link } from "react-router";
import type { Appointment } from "../api/types";
import { formatDayIST, formatIST, formatTimeIST } from "../lib/formatIST";
import { ActionButtons } from "./ActionButtons";
import { CorrectionForm, History, UrgentBadge } from "./AppointmentExtras";
import { CalendarLink } from "./CalendarLink";
import { StatusBadge } from "./common";

/** Everything about one appointment, with the buttons the server allows. */
export function AppointmentCard({ appointment }: { appointment: Appointment }) {
  return (
    <article className="card" aria-label={`Appointment ${appointment.id}`}>
      <h3>
        <Link to={`/patients/${appointment.patient_id}`}>{appointment.patient_name}</Link>{" "}
        <StatusBadge status={appointment.status} />
        <UrgentBadge appointment={appointment} />
        {appointment.needs_attention && (
          <span className="status LATE_CANCELLED"> Needs attention</span>
        )}
      </h3>
      <dl>
        <dt>When</dt>
        <dd>
          {formatDayIST(appointment.start_at_ist)}, {formatTimeIST(appointment.start_at_ist)} to{" "}
          {formatTimeIST(appointment.end_at_ist)} IST
        </dd>
        <dt>Doctor</dt>
        <dd>{appointment.doctor_name}</dd>
        <dt>Phone</dt>
        <dd>{appointment.patient_phone}</dd>
        <dt>Reason</dt>
        <dd>{appointment.reason}</dd>
        {appointment.checked_in_at_ist && (
          <>
            <dt>Arrived</dt>
            <dd>{formatTimeIST(appointment.checked_in_at_ist)} IST</dd>
          </>
        )}
        {appointment.deposit_required_at_booking && (
          <>
            <dt>Deposit</dt>
            <dd>Acknowledged at booking</dd>
          </>
        )}
        {appointment.cancelled_at_ist && (
          <>
            <dt>Cancelled</dt>
            <dd>
              {formatIST(appointment.cancelled_at_ist)} by{" "}
              {appointment.cancelled_by === "CLINIC" ? "the clinic" : "the patient"}
            </dd>
          </>
        )}
      </dl>
      {appointment.needs_attention && (
        <p className="muted">
          This appointment is outside the doctor&apos;s current hours. Move it or cancel it.
        </p>
      )}
      <ActionButtons appointment={appointment} />
      <CorrectionForm appointment={appointment} />
      <History appointmentId={appointment.id} />
      <p>
        <CalendarLink path={`/appointments/${appointment.id}/calendar.ics`} />
      </p>
    </article>
  );
}
