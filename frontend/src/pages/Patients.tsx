import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ApiError, API_BASE } from "../api/client";
import { usePatient, usePatientAppointments, useUpdatePatient } from "../api/hooks";
import type { Patient } from "../api/types";
import { ActionButtons } from "../components/ActionButtons";
import { Banner, ErrorBanner, Skeleton, StatusBadge } from "../components/common";
import { CalendarLink } from "../components/CalendarLink";
import { DepositExplanation } from "../components/DepositNotice";
import { PatientPicker } from "../components/PatientPicker";
import { PatientWaitlist } from "../components/Waitlist";
import { formatDayIST, formatTimeIST } from "../lib/formatIST";

export function PatientSearch() {
  const navigate = useNavigate();
  return (
    <div>
      <h1>Patients</h1>
      <div className="card">
        <PatientPicker onSelect={(patient) => navigate(`/patients/${patient.id}`)} />
      </div>
    </div>
  );
}

/** One patient: details, why they are or are not flagged for a deposit, and their appointments. */
export function PatientDetail() {
  const { id } = useParams();
  const patientId = Number(id) || null;
  const patient = usePatient(patientId);
  const [shown, setShown] = useState(50);
  const history = usePatientAppointments(patientId, shown);

  if (patient.isPending) return <Skeleton rows={4} />;
  if (patient.error) return <ErrorBanner error={patient.error} />;
  const p = patient.data;

  return (
    <div>
      <h1>{p.name}</h1>
      <div className="card">
        <dl>
          <dt>Phone</dt>
          <dd>{p.phone}</dd>
          <dt>Date of birth</dt>
          <dd>{p.date_of_birth}</dd>
          <dt>Deposit required</dt>
          <dd>{p.deposit_required === null ? "Unknown" : p.deposit_required ? "Yes" : "No"}</dd>
        </dl>
        <p>
          <Link className="primary" to={`/book?patient=${p.id}`}>
            Book an appointment for this patient
          </Link>{" "}
          <a href={`${API_BASE}/patients/${p.id}/export`} download={`patient-${p.id}.json`}>
            Download all their records
          </a>
        </p>
      </div>

      <EditPatient key={`${p.id}-${p.name}-${p.phone}-${p.date_of_birth}`} patient={p} />

      <section className="card" aria-label="Deposit status">
        <h2>Deposit status</h2>
        {p.deposit ? <DepositExplanation deposit={p.deposit} /> : null}
        <p className="muted">
          Two late cancellations or no-shows within 30 days mean a deposit must be acknowledged when
          booking.
        </p>
      </section>

      <PatientWaitlist patientId={p.id} deposit={p.deposit} />

      <section aria-label="Appointments">
        <h2>Appointments</h2>
        {history.isPending && <Skeleton rows={3} />}
        {history.error && <ErrorBanner error={history.error} />}
        {history.data && history.data.items.length === 0 && <p className="muted">None yet.</p>}
        {history.data && history.data.items.length > 0 && (
          <table>
            <caption className="visually-hidden">Appointments of {p.name}, newest first</caption>
            <thead>
              <tr>
                <th scope="col">When (IST)</th>
                <th scope="col">Doctor</th>
                <th scope="col">Reason</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.data.items.map((a) => (
                <tr key={a.id}>
                  <td data-label="When">
                    {formatDayIST(a.start_at_ist)}, {formatTimeIST(a.start_at_ist)}
                  </td>
                  <td data-label="Doctor">{a.doctor_name}</td>
                  <td data-label="Reason">{a.reason}</td>
                  <td data-label="Status">
                    <StatusBadge status={a.status} />
                  </td>
                  <td data-label="Actions">
                    <ActionButtons appointment={a} />
                    <CalendarLink path={`/appointments/${a.id}/calendar.ics`} label="Calendar" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {history.data && history.data.total > history.data.items.length && (
          <p>
            <button type="button" onClick={() => setShown((n) => Math.min(n + 50, 100))}>
              Show more ({history.data.items.length} of {history.data.total})
            </button>
          </p>
        )}
      </section>
    </div>
  );
}

/** Correct a name, a phone number or a date of birth. Appointments follow the patient. */
function EditPatient({ patient }: { patient: Patient }) {
  const update = useUpdatePatient();
  const [name, setName] = useState(patient.name);
  const [phone, setPhone] = useState(patient.phone);
  const [birth, setBirth] = useState(patient.date_of_birth);

  const changes = {
    ...(name.trim() !== patient.name ? { name } : {}),
    ...(phone.trim() !== patient.phone ? { phone } : {}),
    ...(birth !== patient.date_of_birth ? { date_of_birth: birth } : {}),
  };
  const dirty = Object.keys(changes).length > 0;
  const duplicates =
    update.error instanceof ApiError && update.error.code === "POSSIBLE_DUPLICATE"
      ? ((update.error.details.candidates as { patient_id: number; name: string }[]) ?? [])
      : null;

  return (
    <form
      className="card"
      aria-label="Edit patient"
      onSubmit={(event) => {
        event.preventDefault();
        update.mutate({ id: patient.id, changes });
      }}
    >
      <h2>Correct details</h2>
      <div className="row">
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
        </label>
        <label>
          Phone
          <input
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            inputMode="tel"
            maxLength={40}
          />
        </label>
        <label>
          Date of birth
          <input
            type="date"
            value={birth}
            onChange={(event) => setBirth(event.target.value)}
            min="1900-01-01"
          />
        </label>
        <button type="submit" className="primary" disabled={!dirty || update.isPending}>
          Save changes
        </button>
      </div>
      {duplicates ? (
        <Banner kind="warn">
          Another patient has this name and date of birth (
          {duplicates.map((match) => `#${match.patient_id}`).join(", ")}). If this is a different
          person,{" "}
          <button
            type="button"
            className="link"
            onClick={() =>
              update.mutate({ id: patient.id, changes: { ...changes, allow_duplicate: true } })
            }
          >
            save anyway
          </button>
          .
        </Banner>
      ) : (
        update.error && <ErrorBanner error={update.error} />
      )}
      {update.isSuccess && !dirty && <Banner kind="success">Saved.</Banner>}
    </form>
  );
}
