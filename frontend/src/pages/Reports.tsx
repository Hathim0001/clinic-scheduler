import { useState } from "react";
import { useDoctors, useReport, useTrends } from "../api/hooks";
import type { DoctorReport, Report, Trends } from "../api/types";
import { BucketChart, DayChart, hourLabel, weekdayLabel } from "../components/charts";
import { ErrorBanner, Skeleton } from "../components/common";
import { DownloadButton } from "../components/DownloadButton";
import { PageHeader } from "../components/ui";
import { addDays } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

const percent = (value: number | null) => (value === null ? "n/a" : `${Math.round(value * 100)}%`);

const MAX_DAYS = 92;
const PRESETS = [7, 30, 90] as const;

const daysBetween = (from: string, to: string) =>
  Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);

/** "3 more than", "2 fewer than" or "the same as": the change against the period before. */
function compare(now: number, before: number, noun: string, days: number): string {
  const period = `the ${days} days before`;
  if (now === before) return `Same as ${period}`;
  const diff = Math.abs(now - before);
  return `${diff} ${now > before ? "more" : "fewer"} ${noun} than ${period}`;
}

function compareRate(now: number | null, before: number | null, days: number): string {
  if (now === null || before === null) return "Nothing to compare with yet";
  const points = Math.round((now - before) * 100);
  if (points === 0) return `Same as the ${days} days before`;
  return `${Math.abs(points)} points ${points > 0 ? "higher" : "lower"} than the ${days} days before`;
}

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

function Headline({
  report,
  before,
  days,
}: {
  report: Report;
  before: Report | undefined;
  days: number;
}) {
  const now = report.total;
  const was = before?.total;
  const alert = now.no_show_rate !== null && now.no_show_rate >= 0.2;
  return (
    <section className="glance" aria-label="The period in numbers">
      <div className="glance-item">
        <div className="glance-label">Visits</div>
        <div className="glance-value">{now.appointments}</div>
        <div className="glance-hint">
          {was ? compare(now.appointments, was.appointments, "visits", days) : " "}
        </div>
      </div>
      <div className="glance-item">
        <div className="glance-label">Completed</div>
        <div className="glance-value">{now.completed}</div>
        <div className="glance-hint">
          {was ? compare(now.completed, was.completed, "completed", days) : " "}
        </div>
      </div>
      <div className={alert ? "glance-item glance-alert" : "glance-item"}>
        <div className="glance-label">No-show rate</div>
        <div className="glance-value">{percent(now.no_show_rate)}</div>
        <div className="glance-hint">
          {was ? compareRate(now.no_show_rate, was.no_show_rate, days) : " "}
        </div>
      </div>
      <div className="glance-item">
        <div className="glance-label">Slots used</div>
        <div className="glance-value">{percent(now.utilisation)}</div>
        <div className="glance-hint">
          {was ? compareRate(now.utilisation, was.utilisation, days) : " "}
        </div>
      </div>
    </section>
  );
}

function ReminderEffect({ effect }: { effect: Trends["reminder_effect"] }) {
  const reminded = effect.reminded_visits;
  const other = effect.other_visits;
  if (reminded === 0) {
    return (
      <p className="empty">
        Once reminders have been sent, this compares how often reminded patients came with everyone
        else.
      </p>
    );
  }
  const rate = (misses: number, visits: number) =>
    visits === 0 ? "n/a" : `${Math.round((misses / visits) * 100)}%`;
  return (
    <dl className="effect">
      <div>
        <dt>Sent a reminder</dt>
        <dd>
          <strong>{rate(effect.reminded_no_shows, reminded)}</strong> missed
          <span className="muted">
            {" "}
            ({effect.reminded_no_shows} of {reminded} visits)
          </span>
        </dd>
      </div>
      <div>
        <dt>No reminder sent</dt>
        <dd>
          <strong>{rate(effect.other_no_shows, other)}</strong> missed
          <span className="muted">
            {" "}
            ({effect.other_no_shows} of {other} visits)
          </span>
        </dd>
      </div>
    </dl>
  );
}

/** How the clinic is doing over a period: the headline figures, the pattern, and the details. */
export default function Reports() {
  const today = useToday();
  const doctors = useDoctors();
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const [doctorId, setDoctorId] = useState<number | null>(null);
  const start = from ?? (today ? addDays(today, -6) : "");
  const end = to ?? today;
  const days = start && end ? daysBetween(start, end) + 1 : 0;

  const report = useReport(start, end);
  const trends = useTrends(start, end, doctorId);
  // The same length of time just before, for "more or fewer than before".
  const previousEnd = start ? addDays(start, -1) : "";
  const previousStart = previousEnd && days > 0 ? addDays(previousEnd, -(days - 1)) : "";
  const before = useReport(days > 0 && days <= MAX_DAYS ? previousStart : "", previousEnd);

  const preset = (length: number) => {
    setFrom(addDays(today, -(length - 1)));
    setTo(today);
  };

  return (
    <div>
      <PageHeader
        title="Report"
        description="How the clinic is doing: visits, no-shows and how full the days are."
      />
      <div className="card">
        <div className="row">
          <label>
            From (India date)
            <input type="date" value={start} onChange={(event) => setFrom(event.target.value)} />
          </label>
          <label>
            To
            <input type="date" value={end} onChange={(event) => setTo(event.target.value)} />
          </label>
          <label>
            Doctor (for the charts)
            <select
              value={doctorId ?? ""}
              onChange={(event) => setDoctorId(Number(event.target.value) || null)}
            >
              <option value="">All doctors</option>
              {doctors.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="segmented" role="group" aria-label="Quick ranges">
          {PRESETS.map((length) => (
            <button
              key={length}
              type="button"
              aria-pressed={days === length && end === today}
              onClick={() => preset(length)}
            >
              Last {length} days
            </button>
          ))}
        </div>
      </div>

      {report.isPending && <Skeleton rows={3} />}
      {report.error && <ErrorBanner error={report.error} onRetry={() => void report.refetch()} />}
      {report.data && <Headline report={report.data} before={before.data} days={days} />}

      <section className="card panel" aria-labelledby="days-heading">
        <div className="panel-head">
          <h2 id="days-heading">Visits each day</h2>
          <DownloadButton
            path="/reports/trends.csv"
            query={{ from: start, to: end, doctor_id: doctorId ?? undefined }}
            fallbackName={`trends-${start}-${end}.csv`}
            label="Download the days as CSV"
          />
        </div>
        {trends.isPending && <Skeleton rows={3} />}
        {trends.error && <ErrorBanner error={trends.error} onRetry={() => void trends.refetch()} />}
        {trends.data && <DayChart days={trends.data.days} />}
      </section>

      {trends.data && (
        <div className="chart-grid">
          <section className="card panel" aria-labelledby="weekday-heading">
            <div className="panel-head">
              <h2 id="weekday-heading">Busiest weekdays</h2>
            </div>
            <BucketChart buckets={trends.data.weekdays} label={weekdayLabel} noun="weekday" />
          </section>
          <section className="card panel" aria-labelledby="hour-heading">
            <div className="panel-head">
              <h2 id="hour-heading">Busiest hours</h2>
            </div>
            {trends.data.hours.length === 0 ? (
              <p className="empty">No visits in this period.</p>
            ) : (
              <BucketChart buckets={trends.data.hours} label={hourLabel} noun="hour" />
            )}
          </section>
          <section className="card panel" aria-labelledby="reminder-heading">
            <div className="panel-head">
              <h2 id="reminder-heading">Do reminders help?</h2>
            </div>
            <ReminderEffect effect={trends.data.reminder_effect} />
          </section>
        </div>
      )}

      <section className="card panel" aria-labelledby="doctor-heading">
        <div className="panel-head">
          <h2 id="doctor-heading">By doctor</h2>
          <DownloadButton
            path="/reports/summary.csv"
            query={{ from: start, to: end }}
            fallbackName={`report-${start}-${end}.csv`}
            label="Download as CSV"
          />
        </div>
        <p className="muted">
          A moved appointment counts once, as rescheduled: not as a cancellation, and its
          replacement is not a new booking. The no-show rate is no-shows out of completed plus
          no-shows. Utilisation is appointments that took a slot out of the slots the doctor&apos;s
          hours offered, so leave days and special hours are taken into account. Freed slots are
          cancellations (not moves); refilled means another appointment with the same doctor later
          took that time, and recovery is refilled out of freed: what the waitlist and walk-ins win
          back. At most {MAX_DAYS} days.
        </p>
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
      </section>
    </div>
  );
}
