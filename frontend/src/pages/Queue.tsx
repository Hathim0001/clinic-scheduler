import { Link, useSearchParams } from "react-router";
import { useClockInfo, useDoctors, useQueue } from "../api/hooks";
import { ActionButtons } from "../components/ActionButtons";
import { UrgentBadge } from "../components/AppointmentExtras";
import { Banner, ErrorBanner, Skeleton, StatusBadge } from "../components/common";
import { Avatar, PageHeader, StatCard } from "../components/ui";
import { useTestClock } from "../lib/clock";
import { formatDayIST, formatTimeIST } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

/** Everything booked for one day, in time order, with the buttons the server allows. */
export default function Queue() {
  const today = useToday();
  const clockInfo = useClockInfo();
  const { setTestClock } = useTestClock();
  const doctors = useDoctors();
  // The filters live in the address, so a queue can be linked to: /queue?date=2026-11-02&doctor=1
  const [params, setParams] = useSearchParams();
  const date = params.get("date") ?? today;
  const doctorId = Number(params.get("doctor")) || null;
  const includeCancelled = params.get("cancelled") === "1";
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  const queue = useQueue(date, doctorId, includeCancelled);
  const seedDay = clockInfo.data?.seed_queue_day ?? null;
  const rows = queue.data ?? [];
  const waiting = rows.filter((a) => a.status === "BOOKED" && !a.checked_in_at_ist).length;
  const arrived = rows.filter((a) => a.status === "BOOKED" && a.checked_in_at_ist).length;
  const seen = rows.filter((a) => a.status === "COMPLETED").length;
  const missed = rows.filter((a) => a.status === "NO_SHOW").length;

  return (
    <div>
      <PageHeader
        title={
          date && date !== today
            ? `Queue for ${formatDayIST(`${date}T12:00:00+05:30`)}`
            : "Today's queue"
        }
        description="Everyone booked for the day, in time order. Check people in as they arrive."
      />
      <div className="card row">
        <label>
          Date (India)
          <input
            type="date"
            value={date}
            onChange={(event) => setParam("date", event.target.value || null)}
          />
        </label>
        <label>
          Doctor
          <select
            value={doctorId ?? ""}
            onChange={(event) => setParam("doctor", event.target.value || null)}
          >
            <option value="">All doctors</option>
            {doctors.data?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={includeCancelled}
            onChange={(event) => setParam("cancelled", event.target.checked ? "1" : null)}
          />
          Show cancelled
        </label>
      </div>

      {rows.length > 0 && (
        <section className="stat-grid compact" aria-label="The queue in numbers">
          <StatCard label="Expected" value={waiting} tone="brand" />
          <StatCard label="In the waiting room" value={arrived} />
          <StatCard label="Seen" value={seen} tone="ok" />
          <StatCard label="Missed" value={missed} tone={missed > 0 ? "danger" : "default"} />
        </section>
      )}

      {queue.error && <ErrorBanner error={queue.error} onRetry={() => void queue.refetch()} />}
      {queue.isPending && date && <Skeleton rows={5} />}

      {queue.data && queue.data.length === 0 && (
        <Banner kind="info">
          No appointments on {date ? formatDayIST(`${date}T12:00:00+05:30`) : "this date"}.
          {seedDay && seedDay !== date && (
            <>
              {" "}
              The demo data has a full queue on {seedDay}:{" "}
              <button
                type="button"
                className="link"
                onClick={() => setTestClock(`${seedDay}T09:30:00+05:30`)}
              >
                set the test clock to that morning
              </button>
              .
            </>
          )}
        </Banner>
      )}

      {queue.data && queue.data.length > 0 && (
        <table className="stack tickets">
          <caption className="visually-hidden">Appointments for {date}</caption>
          <thead>
            <tr>
              <th scope="col">Time (IST)</th>
              <th scope="col">Patient</th>
              <th scope="col">Doctor</th>
              <th scope="col">Reason</th>
              <th scope="col">Status</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {queue.data.map((appointment) => (
              <tr key={appointment.id}>
                <td data-label="Time" className="nowrap">
                  {formatTimeIST(appointment.start_at_ist)}–{formatTimeIST(appointment.end_at_ist)}
                </td>
                <td data-label="Patient">
                  <div className="person">
                    <Avatar name={appointment.patient_name} size="sm" />
                    <div>
                      <Link to={`/patients/${appointment.patient_id}`}>
                        {appointment.patient_name}
                      </Link>
                      <div className="muted">{appointment.patient_phone}</div>
                    </div>
                  </div>
                </td>
                <td data-label="Doctor">{appointment.doctor_name}</td>
                <td data-label="Reason">{appointment.reason}</td>
                <td data-label="Status">
                  <StatusBadge status={appointment.status} />
                  <UrgentBadge appointment={appointment} />
                  {appointment.checked_in_at_ist && appointment.status === "BOOKED" && (
                    <div>Arrived {formatTimeIST(appointment.checked_in_at_ist)}</div>
                  )}
                  {appointment.needs_attention && (
                    <div className="attention-heading">Needs attention</div>
                  )}
                </td>
                <td data-label="Actions">
                  <ActionButtons appointment={appointment} compact />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted">This list refreshes every minute.</p>
    </div>
  );
}
