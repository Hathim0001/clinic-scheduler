import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import {
  useAppointment,
  useBook,
  useDoctors,
  usePatient,
  useReschedule,
  useSlots,
} from "../api/hooks";
import { Banner, ErrorBanner, Skeleton } from "../components/common";
import { DepositCheckbox } from "../components/DepositNotice";
import { PatientPicker } from "../components/PatientPicker";
import { REASON_TEXT } from "../lib/errors";
import { formatDayIST, formatIST, formatTimeIST, istDate } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

/**
 * Book an appointment, or (with ?reschedule=ID) move an existing one. The only times offered are
 * the ones the server says are bookable, so the form cannot ask for something the rules refuse.
 */
export default function Book() {
  const [params] = useSearchParams();
  const rescheduleId = Number(params.get("reschedule")) || null;
  const original = useAppointment(rescheduleId);
  const doctors = useDoctors();
  const today = useToday();

  // What the person has chosen overrides what the link or the original appointment suggests.
  const [pickedDoctor, setPickedDoctor] = useState<number | null>(null);
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  const [pickedPatient, setPickedPatient] = useState<number | null>(
    Number(params.get("patient")) || null,
  );
  const [pickedStart, setPickedStart] = useState<string | null>(params.get("start"));
  const [reason, setReason] = useState("");
  const [depositAcknowledged, setDepositAcknowledged] = useState(false);

  const doctorId =
    pickedDoctor ??
    (Number(params.get("doctor")) || original.data?.doctor_id || doctors.data?.[0]?.id || null);
  const date =
    pickedDate ??
    params.get("date") ??
    (original.data ? istDate(original.data.start_at_ist) : today);
  const patientId = rescheduleId ? (original.data?.patient_id ?? null) : pickedPatient;

  const patient = usePatient(patientId);
  const slots = useSlots(doctorId, date, patientId ?? undefined);
  const doctor = doctors.data?.find((d) => d.id === doctorId);
  const book = useBook();
  const reschedule = useReschedule();

  const offered = slots.data?.slots ?? [];
  const start = pickedStart && offered.some((slot) => slot.start_at_ist === pickedStart) ? pickedStart : null;
  const deposit = patient.data?.deposit ?? null;
  const depositRequired = deposit?.required === true;
  const result = book.data ?? reschedule.data?.new ?? null;
  const error = book.error ?? reschedule.error;
  const pending = book.isPending || reschedule.isPending;

  const ready =
    doctorId !== null &&
    patientId !== null &&
    start !== null &&
    (rescheduleId !== null || reason.trim() !== "") &&
    (!depositRequired || depositAcknowledged);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready || doctorId === null || patientId === null || start === null) return;
    if (rescheduleId !== null) {
      reschedule.mutate({
        id: rescheduleId,
        body: {
          start_at: start,
          doctor_id: doctorId,
          ...(depositRequired ? { deposit_confirmed: depositAcknowledged } : {}),
        },
      });
    } else {
      book.mutate({
        doctor_id: doctorId,
        patient_id: patientId,
        start_at: start,
        reason,
        deposit_confirmed: depositRequired && depositAcknowledged,
      });
    }
  };

  return (
    <div>
      <h1>{rescheduleId ? "Reschedule an appointment" : "Book an appointment"}</h1>

      {rescheduleId && original.data && (
        <Banner kind="info">
          Moving {original.data.patient_name}&apos;s appointment from {formatIST(original.data.start_at_ist)}{" "}
          with {original.data.doctor_name}. The current appointment is cancelled and the new one booked
          together, or neither happens.
        </Banner>
      )}
      {original.error && <ErrorBanner error={original.error} />}

      <form onSubmit={submit}>
        <section className="card" aria-label="Choose the patient">
          <h2>1. Patient</h2>
          {rescheduleId ? (
            <p>{patient.data ? `${patient.data.name}, ${patient.data.phone}` : "Loading…"}</p>
          ) : (
            <>
              <PatientPicker selectedId={patientId} onSelect={(p) => setPickedPatient(p.id)} />
              {patient.data && (
                <p>
                  Selected: <strong>{patient.data.name}</strong>, {patient.data.phone}
                </p>
              )}
            </>
          )}
          {deposit && (
            <DepositCheckbox
              deposit={deposit}
              checked={depositAcknowledged}
              onChange={setDepositAcknowledged}
            />
          )}
        </section>

        <section className="card" aria-label="Doctor and date">
          <h2>2. Doctor and date</h2>
          <div className="row">
            <label>
              Doctor
              <select
                value={doctorId ?? ""}
                onChange={(event) => setPickedDoctor(Number(event.target.value))}
              >
                {doctors.data?.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.speciality})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Date (India)
              <input
                type="date"
                value={date}
                onChange={(event) => setPickedDate(event.target.value)}
              />
            </label>
          </div>
        </section>

        <section className="card" aria-label="Choose a time">
          <h2>3. Time (IST)</h2>
          {slots.isPending && doctorId !== null && date && <Skeleton rows={2} />}
          {slots.error && (
            <ErrorBanner
              error={slots.error}
              doctorName={doctor?.name}
              onRetry={() => void slots.refetch()}
            />
          )}
          {slots.data && offered.length === 0 && (
            <Banner kind="info">
              {slots.data.unavailable_reason
                ? REASON_TEXT[slots.data.unavailable_reason]
                : "No free times."}{" "}
              Try another date or doctor.
            </Banner>
          )}
          {slots.data && offered.length > 0 && (
            <>
              <p className="muted">
                {formatDayIST(`${slots.data.date}T12:00:00+05:30`)}, {slots.data.slot_length_min}-minute
                slots. Only bookable times are listed
                {patientId !== null ? " for this patient" : ""}.
              </p>
              <ul className="slot-list">
                {offered.map((slot) => (
                  <li key={slot.start_at_utc}>
                    <button
                      type="button"
                      className={`slot slot-free${start === slot.start_at_ist ? " slot-selected" : ""}`}
                      aria-pressed={start === slot.start_at_ist}
                      onClick={() => setPickedStart(slot.start_at_ist)}
                    >
                      <span className="time">
                        {formatTimeIST(slot.start_at_ist)}–{formatTimeIST(slot.end_at_ist)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        {!rescheduleId && (
          <section className="card" aria-label="Reason for the visit">
            <h2>4. Reason for the visit</h2>
            <label>
              Reason
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                maxLength={500}
              />
            </label>
          </section>
        )}

        {error && <ErrorBanner error={error} doctorName={doctor?.name} />}
        {result && (
          <Banner kind="success">
            Booked: {result.patient_name} with {result.doctor_name} on {formatIST(result.start_at_ist)}.{" "}
            <Link to={`/day?doctor=${result.doctor_id}&date=${istDate(result.start_at_ist)}`}>
              See the day
            </Link>
          </Banner>
        )}

        <button type="submit" className="primary" disabled={!ready || pending}>
          {pending ? "Saving…" : rescheduleId ? "Move the appointment" : "Book the appointment"}
        </button>
      </form>
    </div>
  );
}
