import { Link, useSearchParams } from "react-router";
import {
  useCheckIn,
  useClockInfo,
  useComplete,
  useDoctors,
  useNoShow,
  useQueue,
} from "../api/hooks";
import type { Appointment } from "../api/types";
import { UrgentBadge } from "../components/AppointmentExtras";
import { useSession } from "../components/AuthGate";
import { Banner, ErrorBanner, Skeleton } from "../components/common";
import { Avatar, PageHeader } from "../components/ui";
import { addDays, formatDayIST, formatTimeIST } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

/** The three things a doctor does to a visit, each shown only when the server allows it. */
function VisitActions({ appointment }: { appointment: Appointment }) {
  const checkIn = useCheckIn();
  const complete = useComplete();
  const noShow = useNoShow();
  const allowed = new Set(appointment.allowed_actions);
  const busy = checkIn.isPending || complete.isPending || noShow.isPending;
  const error = checkIn.error ?? complete.error ?? noShow.error;
  const args = { id: appointment.id, etag: appointment.etag };
  return (
    <div>
      <div className="actions">
        {allowed.has("check-in") && (
          <button type="button" disabled={busy} onClick={() => checkIn.mutate(args)}>
            Check in
          </button>
        )}
        {allowed.has("complete") && (
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => complete.mutate(args)}
          >
            Mark seen
          </button>
        )}
        {allowed.has("no-show") && (
          <button type="button" disabled={busy} onClick={() => noShow.mutate(args)}>
            No-show
          </button>
        )}
      </div>
      {error && <ErrorBanner error={error} />}
    </div>
  );
}

function Visit({ appointment, lead }: { appointment: Appointment; lead?: boolean }) {
  return (
    <li className={lead ? "visit visit-lead" : "visit"}>
      <span className="visit-time">
        {formatTimeIST(appointment.start_at_ist)}
        <span className="muted">–{formatTimeIST(appointment.end_at_ist)}</span>
      </span>
      <Avatar name={appointment.patient_name} size={lead ? "lg" : "md"} />
      <div className="visit-main">
        <Link to={`/patients/${appointment.patient_id}`}>{appointment.patient_name}</Link>
        <span className="muted">
          {appointment.reason}
          {appointment.checked_in_at_ist &&
            ` · arrived ${formatTimeIST(appointment.checked_in_at_ist)}`}
        </span>
        <UrgentBadge appointment={appointment} />
      </div>
      <VisitActions appointment={appointment} />
    </li>
  );
}

/**
 * One doctor's day: who is waiting, who is next, who is still to come and who has been seen.
 * A doctor's own login opens on their own day; reception and administrators choose a doctor.
 */
export default function MyDay() {
  const session = useSession();
  const doctors = useDoctors();
  const today = useToday();
  const clock = useClockInfo();
  const [params, setParams] = useSearchParams();

  const own = session?.role === "DOCTOR" ? (session.doctor_id ?? null) : null;
  const doctorId = own ?? (Number(params.get("doctor")) || doctors.data?.[0]?.id || null);
  const date = params.get("date") ?? today;
  const doctor = doctors.data?.find((d) => d.id === doctorId);
  const queue = useQueue(date, doctorId, false);

  const move = (changes: { doctor?: number; date?: string }) => {
    const next = new URLSearchParams(params);
    if (changes.doctor !== undefined) next.set("doctor", String(changes.doctor));
    if (changes.date !== undefined) next.set("date", changes.date);
    setParams(next);
  };

  const rows = [...(queue.data ?? [])].sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc));
  const now = clock.data?.now_utc ?? "";
  const waiting = rows
    .filter((a) => a.status === "BOOKED" && a.checked_in_at_ist)
    .sort((a, b) => (a.checked_in_at_utc ?? "").localeCompare(b.checked_in_at_utc ?? ""));
  const ahead = rows.filter((a) => a.status === "BOOKED" && !a.checked_in_at_ist);
  const next = ahead.find((a) => a.end_at_utc >= now);
  const seen = rows.filter((a) => a.status === "COMPLETED");
  const missed = rows.filter((a) => a.status === "NO_SHOW");
  // Whoever has arrived comes first; with nobody waiting, the next patient expected.
  const lead = waiting[0] ?? next;
  const rest = waiting.filter((a) => a !== lead);
  const later = ahead.filter((a) => a !== lead);
  const isToday = date === today;

  return (
    <div className="my-day">
      <PageHeader
        title={own !== null ? "My day" : "A doctor's day"}
        description={
          doctor
            ? `${doctor.name} · ${doctor.speciality} · ${date ? formatDayIST(`${date}T12:00:00+05:30`) : ""}`
            : undefined
        }
      />

      <div className="card row">
        {own === null && (
          <label>
            Doctor
            <select
              value={doctorId ?? ""}
              onChange={(event) => move({ doctor: Number(event.target.value) })}
            >
              {doctors.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.speciality})
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Date (India)
          <input
            type="date"
            value={date}
            onChange={(event) => event.target.value && move({ date: event.target.value })}
          />
        </label>
        <button type="button" onClick={() => date && move({ date: addDays(date, -1) })}>
          Previous day
        </button>
        <button type="button" onClick={() => today && move({ date: today })}>
          Today
        </button>
        <button type="button" onClick={() => date && move({ date: addDays(date, 1) })}>
          Next day
        </button>
      </div>

      {queue.isPending && doctorId !== null && <Skeleton rows={4} />}
      {queue.error && <ErrorBanner error={queue.error} onRetry={() => void queue.refetch()} />}
      {doctors.data && doctorId === null && (
        <Banner kind="info">This login is not linked to a doctor yet. Ask an administrator.</Banner>
      )}

      {queue.data && (
        <>
          <section className="glance" aria-label="The day in numbers">
            <div className="glance-item">
              <div className="glance-label">Booked</div>
              <div className="glance-value">{rows.length}</div>
              <div className="glance-hint">Visits on this day</div>
            </div>
            <div className="glance-item">
              <div className="glance-label">Waiting now</div>
              <div className="glance-value">{waiting.length}</div>
              <div className="glance-hint">Arrived, not yet seen</div>
            </div>
            <div className="glance-item">
              <div className="glance-label">Still to come</div>
              <div className="glance-value">{ahead.length}</div>
              <div className="glance-hint">Not arrived yet</div>
            </div>
            <div className="glance-item">
              <div className="glance-label">Seen</div>
              <div className="glance-value">{seen.length}</div>
              <div className="glance-hint">
                {missed.length > 0 ? `${missed.length} did not come` : "Visits completed"}
              </div>
            </div>
          </section>

          {rows.length === 0 && (
            <Banner kind="info">No visits are booked for this day{isToday ? " yet" : ""}.</Banner>
          )}

          {lead && (
            <section className="card panel" aria-labelledby="lead-heading">
              <div className="panel-head">
                <h2 id="lead-heading">
                  {lead.checked_in_at_ist ? "Waiting for you" : "Next patient"}
                </h2>
              </div>
              <ul className="visits">
                <Visit appointment={lead} lead />
              </ul>
            </section>
          )}

          {(rest.length > 0 || later.length > 0) && (
            <section className="card panel" aria-labelledby="later-heading">
              <div className="panel-head">
                <h2 id="later-heading">
                  {rest.length > 0 ? "Also waiting, then later" : "Later today"}
                </h2>
              </div>
              <ul className="visits">
                {[...rest, ...later].map((a) => (
                  <Visit key={a.id} appointment={a} />
                ))}
              </ul>
            </section>
          )}

          {seen.length + missed.length > 0 && (
            <section className="card panel" aria-labelledby="done-heading">
              <div className="panel-head">
                <h2 id="done-heading">Done</h2>
              </div>
              <ul className="visits">
                {[...seen, ...missed]
                  .sort((a, b) => a.start_at_utc.localeCompare(b.start_at_utc))
                  .map((a) => (
                    <li key={a.id} className="visit visit-done">
                      <span className="visit-time">{formatTimeIST(a.start_at_ist)}</span>
                      <Avatar name={a.patient_name} size="sm" />
                      <div className="visit-main">
                        <Link to={`/patients/${a.patient_id}`}>{a.patient_name}</Link>
                        <span className="muted">{a.reason}</span>
                      </div>
                      <span className={a.status === "COMPLETED" ? "chip chip-ok" : "chip"}>
                        {a.status === "COMPLETED" ? "Seen" : "Did not come"}
                      </span>
                    </li>
                  ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
