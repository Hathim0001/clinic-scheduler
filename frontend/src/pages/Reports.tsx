import { useState } from "react";
import { useReport } from "../api/hooks";
import type { DoctorReport } from "../api/types";
import { ErrorBanner, Skeleton } from "../components/common";
import { addDays } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

const percent = (value: number | null) => (value === null ? "n/a" : `${Math.round(value * 100)}%`);

function Row({ row }: { row: DoctorReport }) {
  return (
    <tr>
      <th scope="row">{row.doctor_name}</th>
      <td data-label="Appointments">{row.appointments}</td>
      <td data-label="New bookings">{row.new_bookings}</td>
      <td data-label="Completed">{row.completed}</td>
      <td data-label="No-shows">{row.no_show}</td>
      <td data-label="Cancelled">{row.cancelled}</td>
      <td data-label="Late cancels">{row.late_cancelled}</td>
      <td data-label="Rescheduled">{row.rescheduled}</td>
      <td data-label="Still booked">{row.booked}</td>
      <td data-label="Slots offered">{row.capacity_slots}</td>
      <td data-label="Utilisation">{percent(row.utilisation)}</td>
      <td data-label="No-show rate">{percent(row.no_show_rate)}</td>
      <td data-label="Freed slots">{row.freed_slots}</td>
      <td data-label="Refilled">
        {row.refilled}
        {row.refilled_via_waitlist > 0 ? ` (${row.refilled_via_waitlist} via waitlist)` : ""}
      </td>
      <td data-label="Recovery">{percent(row.recovery_rate)}</td>
    </tr>
  );
}

/** Counts per doctor for a range of India dates. Definitions are in the README. */
export default function Reports() {
  const today = useToday();
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const start = from ?? (today ? addDays(today, -6) : "");
  const end = to ?? today;
  const report = useReport(start, end);

  return (
    <div>
      <h1>Report</h1>
      <div className="card row">
        <label>
          From (India date)
          <input type="date" value={start} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label>
          To
          <input type="date" value={end} onChange={(event) => setTo(event.target.value)} />
        </label>
      </div>
      <p className="muted">
        A moved appointment counts once, as rescheduled: not as a cancellation, and its replacement
        is not a new booking. The no-show rate is no-shows out of completed plus no-shows.
        Utilisation is appointments that took a slot out of the slots the doctor&apos;s hours
        offered, so leave days and special hours are taken into account. Freed slots are
        cancellations (not moves); refilled means another appointment with the same doctor later
        took that time, and recovery is refilled out of freed: what the waitlist and walk-ins win
        back. At most 92 days.
      </p>
      {report.isPending && <Skeleton rows={4} />}
      {report.error && <ErrorBanner error={report.error} onRetry={() => void report.refetch()} />}
      {report.data && (
        <div className="table-scroll" role="region" aria-label="Report by doctor" tabIndex={0}>
          <table>
            <caption className="visually-hidden">
              Appointments from {start} to {end}
            </caption>
            <thead>
              <tr>
                <th scope="col">Doctor</th>
                <th scope="col">Appointments</th>
                <th scope="col">New bookings</th>
                <th scope="col">Completed</th>
                <th scope="col">No-shows</th>
                <th scope="col">Cancelled</th>
                <th scope="col">Late cancels</th>
                <th scope="col">Rescheduled</th>
                <th scope="col">Still booked</th>
                <th scope="col">Slots offered</th>
                <th scope="col">Utilisation</th>
                <th scope="col">No-show rate</th>
                <th scope="col">Freed slots</th>
                <th scope="col">Refilled</th>
                <th scope="col">Recovery</th>
              </tr>
            </thead>
            <tbody>
              {report.data.doctors.map((row) => (
                <Row key={row.doctor_id} row={row} />
              ))}
              <Row row={report.data.total} />
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
