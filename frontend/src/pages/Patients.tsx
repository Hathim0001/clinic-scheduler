import { Link, useNavigate, useParams } from "react-router";
import { usePatient, usePatientAppointments } from "../api/hooks";
import { ActionButtons } from "../components/ActionButtons";
import { ErrorBanner, Skeleton, StatusBadge } from "../components/common";
import { DepositExplanation } from "../components/DepositNotice";
import { PatientPicker } from "../components/PatientPicker";
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
  const history = usePatientAppointments(patientId);

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
        </dl>
        <p>
          <Link className="primary" to={`/book?patient=${p.id}`}>
            Book an appointment for this patient
          </Link>
        </p>
      </div>

      <section className="card" aria-label="Deposit status">
        <h2>Deposit status</h2>
        {p.deposit ? <DepositExplanation deposit={p.deposit} /> : null}
        <p className="muted">
          Two late cancellations or no-shows within 30 days mean a deposit must be acknowledged when
          booking.
        </p>
      </section>

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
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
