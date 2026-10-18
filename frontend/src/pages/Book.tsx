import { useTriage } from "../api/hooks";
import { BookedBanner } from "../components/booking/BookedBanner";
import { DoctorDateFields } from "../components/booking/DoctorDateFields";
import { RepeatFields } from "../components/booking/RepeatFields";
import {
  isLateMoveQuestion,
  LateMoveQuestion,
  MoverFieldset,
} from "../components/booking/RescheduleNotices";
import { SlotPicker } from "../components/booking/SlotPicker";
import { useBookingForm } from "../components/booking/useBookingForm";
import { Banner, ErrorBanner } from "../components/common";
import { DepositCheckbox } from "../components/DepositNotice";
import { PatientPicker } from "../components/PatientPicker";
import { JoinWaitlist } from "../components/Waitlist";
import { formatIST } from "../lib/formatIST";
import { useDebounced } from "../lib/useDebounced";

/**
 * Book an appointment, or (with ?reschedule=ID) move an existing one. The only times offered are
 * the ones the server says are bookable, so the form cannot ask for something the rules refuse.
 * The decisions live in `useBookingForm`; this file is the layout.
 */
export default function Book() {
  const form = useBookingForm();
  const f = form.fields;
  const { rescheduleId, doctor, doctorId, patientId, patient, original } = form;
  const triage = useTriage(useDebounced(f.reason));
  const lateQuestion = isLateMoveQuestion(form.reschedule.error) ? form.reschedule.error : null;

  return (
    <div>
      <h1>{rescheduleId ? "Reschedule an appointment" : "Book an appointment"}</h1>

      {rescheduleId && original.data && (
        <Banner kind="info">
          Moving {original.data.patient_name}&apos;s appointment from{" "}
          {formatIST(original.data.start_at_ist)} with {original.data.doctor_name}. The current
          appointment is cancelled and the new one booked together, or neither happens.
        </Banner>
      )}
      {original.error && <ErrorBanner error={original.error} />}

      {/* Outside the form on purpose: registering a patient is a form of its own. */}
      <section className="card" aria-label="Choose the patient">
        <h2>1. Patient</h2>
        {rescheduleId ? (
          <p>{patient.data ? `${patient.data.name}, ${patient.data.phone}` : "Loading…"}</p>
        ) : (
          <>
            <PatientPicker selectedId={patientId} onSelect={(p) => f.setPickedPatient(p.id)} />
            {patient.data && (
              <p>
                Selected: <strong>{patient.data.name}</strong>, {patient.data.phone}
              </p>
            )}
          </>
        )}
        {form.deposit && (
          <DepositCheckbox
            deposit={form.deposit}
            checked={f.depositAcknowledged}
            onChange={f.setDepositAcknowledged}
          />
        )}
      </section>

      <form onSubmit={form.submit}>
        <section className="card" aria-label="Doctor and date">
          <h2>2. Doctor and date</h2>
          <DoctorDateFields
            doctors={form.doctors.data}
            doctorId={doctorId}
            onDoctor={f.setPickedDoctor}
            date={form.date}
            onDate={f.setPickedDate}
            visit={
              !rescheduleId && doctor
                ? { doctor, slots: f.visitSlots, onSlots: f.setVisitSlots }
                : undefined
            }
          />
          {rescheduleId !== null && form.lengthInSlots === null && doctor && (
            <Banner kind="error">
              This visit lasts {form.movedMinutes} minutes, which does not fit {doctor.name}&apos;s{" "}
              {doctor.slot_length_min}-minute slots. Choose another doctor.
            </Banner>
          )}
        </section>

        <section className="card" aria-label="Choose a time">
          <h2>3. Time (IST)</h2>
          <SlotPicker
            slots={form.slots}
            offered={form.offered}
            start={form.start}
            onPick={f.setPickedStart}
            doctorName={doctor?.name}
            forPatient={patientId !== null}
            loading={doctorId !== null && form.date !== ""}
          />
          {form.slots.data && form.offered.length === 0 && !rescheduleId && doctorId !== null && (
            <JoinWaitlist doctorId={doctorId} patientId={patientId} date={form.date} />
          )}
        </section>

        {!rescheduleId && (
          <section className="card" aria-label="Reason for the visit">
            <h2>4. Reason for the visit</h2>
            <label>
              Reason
              <textarea
                value={f.reason}
                onChange={(event) => f.setReason(event.target.value)}
                maxLength={500}
              />
            </label>
            {triage.data?.urgent && <Banner kind="error">{triage.data.message}</Banner>}
            <RepeatFields
              repeat={f.repeat}
              onRepeat={f.setRepeat}
              everyDays={f.everyDays}
              onEveryDays={f.setEveryDays}
              count={f.count}
              onCount={f.setCount}
            />
          </section>
        )}

        {rescheduleId !== null && <MoverFieldset mover={f.mover} onChange={f.setMover} />}

        {lateQuestion && (
          <LateMoveQuestion
            error={lateQuestion}
            pending={form.pending}
            onConfirm={() => form.move(true)}
            onClinicInstead={() => f.setMover("CLINIC")}
          />
        )}
        {form.error && !lateQuestion && (
          <ErrorBanner error={form.error} doctorName={doctor?.name} />
        )}
        {form.result && (
          <BookedBanner result={form.result} more={Math.max(form.seriesLength - 1, 0)} />
        )}

        <button type="submit" className="primary" disabled={!form.ready || form.pending}>
          {form.pending
            ? "Saving…"
            : rescheduleId
              ? "Move the appointment"
              : "Book the appointment"}
        </button>
      </form>
    </div>
  );
}
