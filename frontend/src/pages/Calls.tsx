import { useConfirmByPhone, useQueue } from "../api/hooks";
import type { Appointment } from "../api/types";
import { Banner, ErrorBanner, Skeleton } from "../components/common";
import { addDays, formatDayIST, formatTimeIST } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

/**
 * Tomorrow's calls: who to ring to confirm. Reviews of reminder studies find a telephone reminder
 * helps attendance more reliably than a text, and this needs no message gateway: reception rings
 * the patient and presses Called.
 */
export default function Calls() {
  const today = useToday();
  const tomorrow = today ? addDays(today, 1) : "";
  const queue = useQueue(tomorrow, null, false);
  const booked = (queue.data ?? []).filter((a) => a.status === "BOOKED");
  const done = booked.filter((a) => a.confirmed_by_phone_at_utc !== null).length;

  return (
    <div>
      <h1>Calls for tomorrow</h1>
      <p className="muted">
        {tomorrow ? `${formatDayIST(`${tomorrow}T12:00:00+05:30`)}. ` : ""}
        Ring each patient, then press Called so the next person can see it is done.
      </p>
      {queue.isPending && <Skeleton rows={3} />}
      {queue.error && <ErrorBanner error={queue.error} onRetry={() => void queue.refetch()} />}
      {queue.data && booked.length === 0 && <Banner kind="info">Nothing to confirm.</Banner>}
      {booked.length > 0 && (
        <>
          <p aria-live="polite">
            {done} of {booked.length} confirmed by phone.
          </p>
          <div className="table-scroll" role="region" aria-label="Calls" tabIndex={0}>
            <table className="stack">
              <caption className="visually-hidden">Appointments to confirm by phone</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Patient</th>
                  <th scope="col">Phone</th>
                  <th scope="col">Doctor</th>
                  <th scope="col">Confirmed</th>
                </tr>
              </thead>
              <tbody>
                {booked.map((a) => (
                  <CallRow key={a.id} appointment={a} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function CallRow({ appointment: a }: { appointment: Appointment }) {
  const confirm = useConfirmByPhone();
  return (
    <tr>
      <td data-label="Time">{formatTimeIST(a.start_at_ist)}</td>
      <th scope="row" data-label="Patient">
        {a.patient_name}
      </th>
      <td data-label="Phone">
        <a href={`tel:${a.patient_phone}`}>{a.patient_phone}</a>
      </td>
      <td data-label="Doctor">{a.doctor_name}</td>
      <td data-label="Confirmed">
        {a.confirmed_by_phone_at_utc ? (
          "Yes"
        ) : (
          <button
            type="button"
            onClick={() => confirm.mutate(a.id)}
            disabled={confirm.isPending}
            aria-label={`Mark ${a.patient_name} as called`}
          >
            Called
          </button>
        )}
        {confirm.error && <ErrorBanner error={confirm.error} />}
      </td>
    </tr>
  );
}
