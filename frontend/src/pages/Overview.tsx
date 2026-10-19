import { Link } from "react-router";
import {
  useClockInfo,
  useDoctors,
  useNeedsAttention,
  usePendingMessages,
  useQueue,
  useSchedule,
} from "../api/hooks";
import type { Doctor } from "../api/types";
import { ErrorBanner, Skeleton } from "../components/common";
import { Avatar, Icon, Meter, PageHeader, StatCard } from "../components/ui";
import { formatDayIST, formatTimeIST } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

/** How full one doctor's day is, and the next time a patient could be booked. */
function DoctorLoad({ doctor, date }: { doctor: Doctor; date: string }) {
  const schedule = useSchedule(doctor.id, date);
  const slots = schedule.data?.slots ?? [];
  const booked = slots.filter((s) => s.state === "BOOKED").length;
  const next = slots.find((s) => s.state === "FREE");
  const working = slots.length > 0;

  return (
    <li className="load-row">
      <Avatar name={doctor.name} />
      <div className="load-main">
        <div className="load-title">
          <Link to={`/day?doctor=${doctor.id}&date=${date}`}>{doctor.name}</Link>
          <span className="muted">{doctor.speciality}</span>
        </div>
        {schedule.isPending ? (
          <span className="muted">Loading…</span>
        ) : working ? (
          <>
            <Meter value={booked} max={slots.length} label={`${doctor.name} bookings today`} />
            <div className="load-figures">
              <span>
                <strong>{booked}</strong> of {slots.length} slots booked
              </span>
              {next ? (
                <Link to={`/book?doctor=${doctor.id}&date=${date}`}>
                  Next free {formatTimeIST(next.start_at_ist)}
                </Link>
              ) : (
                <span className="muted">No free slots left</span>
              )}
            </div>
          </>
        ) : (
          <span className="muted">Not seeing patients today.</span>
        )}
      </div>
    </li>
  );
}

/** The front desk's morning view: how the day is going, who is next, and what needs a look. */
export default function Overview() {
  const today = useToday();
  const clock = useClockInfo();
  const doctors = useDoctors();
  const queue = useQueue(today, null, false);
  const attention = useNeedsAttention();
  const messages = usePendingMessages();

  const now = clock.data?.now_utc ?? "";
  const all = queue.data ?? [];
  const arrived = all.filter((a) => a.status === "BOOKED" && a.checked_in_at_ist).length;
  const seen = all.filter((a) => a.status === "COMPLETED").length;
  const missed = all.filter((a) => a.status === "NO_SHOW").length;
  const upcoming = all.filter((a) => a.status === "BOOKED" && a.end_at_utc >= now);
  const needsAttention = attention.data?.total ?? 0;
  const messagesWaiting = messages.data?.count ?? 0;

  return (
    <div className="overview">
      <PageHeader
        title="Overview"
        description={
          today ? `${formatDayIST(`${today}T12:00:00+05:30`)} · all times India (IST)` : undefined
        }
      />

      {queue.error && <ErrorBanner error={queue.error} onRetry={() => void queue.refetch()} />}

      <section className="stat-grid" aria-label="Today in numbers">
        <StatCard
          icon="calendar"
          tone="brand"
          label="Visits today"
          value={queue.isPending ? "–" : all.length}
          hint={`${upcoming.length} still to come`}
        />
        <StatCard
          icon="people"
          label="Arrived"
          value={queue.isPending ? "–" : arrived}
          hint="Checked in, not yet seen"
        />
        <StatCard
          icon="check"
          tone="ok"
          label="Seen"
          value={queue.isPending ? "–" : seen}
          hint="Visits completed"
        />
        <StatCard
          icon="alert"
          tone={missed > 0 ? "danger" : "default"}
          label="Missed"
          value={queue.isPending ? "–" : missed}
          hint="Patients who did not come"
        />
      </section>

      <div className="overview-grid">
        <section className="card panel" aria-labelledby="next-heading">
          <div className="panel-head">
            <h2 id="next-heading">Up next</h2>
            <Link to="/queue">Full queue</Link>
          </div>
          {queue.isPending && <Skeleton rows={4} />}
          {queue.data && upcoming.length === 0 && (
            <p className="empty">
              {all.length === 0
                ? "No visits are booked for today."
                : "Nobody else is booked for the rest of today."}
            </p>
          )}
          {upcoming.length > 0 && (
            <ul className="list-rows">
              {upcoming.slice(0, 6).map((a) => (
                <li key={a.id} className="list-row">
                  <span className="list-time">{formatTimeIST(a.start_at_ist)}</span>
                  <Avatar name={a.patient_name} size="sm" />
                  <span className="list-main">
                    <Link to={`/patients/${a.patient_id}`}>{a.patient_name}</Link>
                    <span className="muted">
                      {a.reason} · {a.doctor_name}
                    </span>
                  </span>
                  {a.checked_in_at_ist ? (
                    <span className="chip chip-ok">Arrived</span>
                  ) : (
                    <span className="chip">Expected</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="overview-side">
          <section className="card panel" aria-labelledby="load-heading">
            <div className="panel-head">
              <h2 id="load-heading">Doctors today</h2>
              <Link to="/day">Day view</Link>
            </div>
            {doctors.isPending && <Skeleton rows={2} />}
            {doctors.error && <ErrorBanner error={doctors.error} />}
            <ul className="load-list">
              {doctors.data?.map((d) => (
                <DoctorLoad key={d.id} doctor={d} date={today} />
              ))}
            </ul>
          </section>

          <section className="card panel" aria-labelledby="todo-heading">
            <div className="panel-head">
              <h2 id="todo-heading">Needs a look</h2>
            </div>
            {needsAttention === 0 && messagesWaiting === 0 ? (
              <p className="empty">
                <Icon name="check" size={16} /> All clear: nothing is waiting on the desk.
              </p>
            ) : (
              <ul className="todo-list">
                {needsAttention > 0 && (
                  <li>
                    <Link to="/admin">
                      <strong>{needsAttention}</strong>{" "}
                      {needsAttention === 1 ? "appointment" : "appointments"} outside the
                      doctor&apos;s hours
                    </Link>
                  </li>
                )}
                {messagesWaiting > 0 && (
                  <li>
                    <Link to="/messages">
                      <strong>{messagesWaiting}</strong>{" "}
                      {messagesWaiting === 1 ? "message" : "messages"} waiting to be sent
                    </Link>
                  </li>
                )}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
