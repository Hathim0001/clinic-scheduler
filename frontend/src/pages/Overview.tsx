import { Link } from "react-router";
import {
  useClockInfo,
  useDoctors,
  useNeedsAttention,
  usePendingMessages,
  useQueue,
  useSchedule,
} from "../api/hooks";
import type { Doctor, ScheduleSlot, SlotState } from "../api/types";
import { ErrorBanner, Skeleton } from "../components/common";
import { Avatar, Icon, PageHeader } from "../components/ui";
import { formatDayIST, formatTimeIST } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

const CELL_CLASS: Record<SlotState, string> = {
  BOOKED: "cell-booked",
  FREE: "cell-free",
  PAST: "cell-past",
  CAPPED: "cell-closed",
  CLOSED: "cell-closed",
  BUSY: "cell-closed",
};

/** The slot the "now" tick stands before: the first one starting at or after now (never the first). */
function nowIndex(slots: ScheduleSlot[], now: string): number {
  if (!now) return -1;
  const at = Date.parse(now);
  const first = slots.findIndex((s) => Date.parse(s.start_at_utc) >= at);
  return first > 0 ? first : -1;
}

/**
 * One doctor's day drawn as a strip, one cell per slot: filled when booked, open when free, faded
 * when it has passed. A marigold tick marks where "now" falls. The words beside it carry the same
 * facts, so the picture is never the only way to read it.
 */
function DayRibbon({
  slots,
  summary,
  now,
}: {
  slots: ScheduleSlot[];
  summary: string;
  now: string;
}) {
  const nowAt = nowIndex(slots, now);
  return (
    <div className="ribbon" role="img" aria-label={summary}>
      {slots.map((slot, index) => (
        <span key={slot.start_at_utc} className="ribbon-slot" aria-hidden="true">
          {index === nowAt && <span className="ribbon-now" />}
          <span className={`cell ${CELL_CLASS[slot.state]}`} />
        </span>
      ))}
    </div>
  );
}

/** How full one doctor's day is, and the next time a patient could be booked. */
function DoctorDay({ doctor, date, now }: { doctor: Doctor; date: string; now: string }) {
  const schedule = useSchedule(doctor.id, date);
  const slots = schedule.data?.slots ?? [];
  const booked = slots.filter((s) => s.state === "BOOKED").length;
  const next = slots.find((s) => s.state === "FREE");
  const working = slots.length > 0;

  return (
    <li className="doctor-day">
      <div className="doctor-day-head">
        <Avatar name={doctor.name} />
        <div className="doctor-day-name">
          <Link to={`/day?doctor=${doctor.id}&date=${date}`}>{doctor.name}</Link>
          <span className="muted">{doctor.speciality}</span>
        </div>
        {working && (
          <span className="doctor-day-figures">
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
          </span>
        )}
      </div>
      {schedule.isPending && <span className="muted">Loading the day…</span>}
      {!schedule.isPending && !working && (
        <p className="muted doctor-day-off">Not seeing patients today.</p>
      )}
      {working && (
        <DayRibbon
          now={now}
          slots={slots}
          summary={`${doctor.name}: ${booked} of ${slots.length} slots booked${
            next ? `, next free at ${formatTimeIST(next.start_at_ist)}` : ""
          }`}
        />
      )}
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
  const figure = (value: number) => (queue.isPending ? "–" : value);

  return (
    <div className="overview">
      <PageHeader
        title="Overview"
        description={
          today ? `${formatDayIST(`${today}T12:00:00+05:30`)} · all times India (IST)` : undefined
        }
      />

      {queue.error && <ErrorBanner error={queue.error} onRetry={() => void queue.refetch()} />}

      <section className="glance" aria-label="Today in numbers">
        <div className="glance-item">
          <div className="glance-label">Visits today</div>
          <div className="glance-value">{figure(all.length)}</div>
          <div className="glance-hint">{upcoming.length} still to come</div>
        </div>
        <div className="glance-item">
          <div className="glance-label">Arrived</div>
          <div className="glance-value">{figure(arrived)}</div>
          <div className="glance-hint">Checked in, not yet seen</div>
        </div>
        <div className="glance-item">
          <div className="glance-label">Seen</div>
          <div className="glance-value">{figure(seen)}</div>
          <div className="glance-hint">Visits completed</div>
        </div>
        <div className={missed > 0 ? "glance-item glance-alert" : "glance-item"}>
          <div className="glance-label">Missed</div>
          <div className="glance-value">{figure(missed)}</div>
          <div className="glance-hint">Patients who did not come</div>
        </div>
      </section>

      <section className="card panel" aria-labelledby="load-heading">
        <div className="panel-head">
          <h2 id="load-heading">Doctors today</h2>
          <Link to="/day">Open the day view</Link>
        </div>
        {doctors.isPending && <Skeleton rows={2} />}
        {doctors.error && <ErrorBanner error={doctors.error} />}
        <ul className="doctor-days">
          {doctors.data?.map((d) => (
            <DoctorDay key={d.id} doctor={d} date={today} now={now} />
          ))}
        </ul>
        <ul className="ribbon-key" aria-label="How to read the strips">
          <li>
            <span className="cell cell-booked" /> Booked
          </li>
          <li>
            <span className="cell cell-free" /> Free
          </li>
          <li>
            <span className="cell cell-past" /> Already passed
          </li>
          <li>
            <span className="ribbon-now-key" /> Now
          </li>
        </ul>
      </section>

      <div className="overview-grid">
        <section className="card panel" aria-labelledby="next-heading">
          <div className="panel-head">
            <h2 id="next-heading">Up next</h2>
            <Link to="/queue">Open the queue</Link>
          </div>
          {queue.isPending && <Skeleton rows={4} />}
          {queue.data && upcoming.length === 0 && (
            <p className="empty">
              {all.length === 0
                ? "No visits are booked for today. Book one when someone calls."
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
  );
}
