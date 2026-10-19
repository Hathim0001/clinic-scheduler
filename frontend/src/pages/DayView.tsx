import { useState, type KeyboardEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useAppointment, useDoctors, useSchedule } from "../api/hooks";
import type { SlotState } from "../api/types";
import { AppointmentCard } from "../components/AppointmentCard";
import { Banner, ErrorBanner, Skeleton, StatusBadge } from "../components/common";
import { DaySummary } from "../components/DaySummary";
import { Avatar, PageHeader } from "../components/ui";
import { DayWaitlist } from "../components/Waitlist";
import { addDays, formatDayIST, formatTimeIST } from "../lib/formatIST";
import { REASON_TEXT } from "../lib/errors";
import { useToday } from "../lib/useToday";

const STATE_TEXT: Record<SlotState, string> = {
  FREE: "Free",
  BOOKED: "Booked",
  PAST: "Past",
  CAPPED: "Daily limit reached",
  CLOSED: "Not open for booking yet",
  BUSY: "Patient is busy",
};

/** One doctor, one India date: every slot with its state. Click a free slot to book it. */
export default function DayView() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const doctors = useDoctors();
  const today = useToday();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const doctorId = Number(params.get("doctor")) || doctors.data?.[0]?.id || null;
  const date = params.get("date") ?? today;
  const schedule = useSchedule(doctorId, date);
  const selected = useAppointment(selectedId);
  const doctor = doctors.data?.find((d) => d.id === doctorId);

  const update = (changes: { doctor?: number; date?: string }) => {
    const next = new URLSearchParams(params);
    if (changes.doctor !== undefined) next.set("doctor", String(changes.doctor));
    if (changes.date !== undefined) next.set("date", changes.date);
    setParams(next);
    setSelectedId(null);
  };

  // Up and Down arrows step through the slots, so a front desk can run the day from the keyboard.
  const moveBetweenSlots = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const slots = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>("button.slot"),
    );
    const at = slots.indexOf(document.activeElement as HTMLButtonElement);
    if (at === -1) return;
    event.preventDefault();
    slots[at + (event.key === "ArrowDown" ? 1 : -1)]?.focus();
  };

  const bookingLink = (startIst: string) =>
    `/book?doctor=${doctorId}&date=${schedule.data?.date ?? date}&start=${encodeURIComponent(startIst)}`;

  const hours = schedule.data?.windows.map((w) => `${w.start}–${w.end}`).join(", ");

  return (
    <div>
      <PageHeader
        title="Day view"
        description={
          doctor
            ? `${doctor.name} · ${doctor.speciality} · ${doctor.slot_length_min}-minute slots`
            : undefined
        }
      />
      <div className="card row">
        <label>
          Doctor
          <select
            value={doctorId ?? ""}
            onChange={(event) => update({ doctor: Number(event.target.value) })}
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
            onChange={(event) => update({ date: event.target.value })}
          />
        </label>
        <button type="button" onClick={() => date && update({ date: addDays(date, -1) })}>
          Previous day
        </button>
        <button type="button" onClick={() => today && update({ date: today })}>
          Today
        </button>
        <button type="button" onClick={() => date && update({ date: addDays(date, 1) })}>
          Next day
        </button>
      </div>

      {doctors.error && (
        <ErrorBanner error={doctors.error} onRetry={() => void doctors.refetch()} />
      )}
      {schedule.error && (
        <ErrorBanner
          error={schedule.error}
          doctorName={doctor?.name}
          onRetry={() => void schedule.refetch()}
        />
      )}
      {schedule.isPending && doctorId !== null && date && <Skeleton rows={6} />}

      {schedule.data && (
        <div className="grid-2">
          <section aria-label="Slots">
            <h2>
              {formatDayIST(`${schedule.data.date}T12:00:00+05:30`)}{" "}
              <span className="muted">
                {schedule.data.slots.length > 0
                  ? `${hours} IST${schedule.data.source === "OVERRIDE" ? " (special hours for this date)" : ""}`
                  : ""}
              </span>
            </h2>
            {schedule.data.unavailable_reason && (
              <Banner kind="info">
                {REASON_TEXT[schedule.data.unavailable_reason] ?? schedule.data.unavailable_reason}
                {schedule.data.source === "OVERRIDE" && schedule.data.slots.length === 0
                  ? " (a leave day or special hours were set for this date)"
                  : ""}
              </Banner>
            )}
            <ul className="timetable" onKeyDown={moveBetweenSlots}>
              {schedule.data.slots.map((slot) => {
                const time = `${formatTimeIST(slot.start_at_ist)}–${formatTimeIST(slot.end_at_ist)}`;
                if (slot.state === "FREE") {
                  return (
                    <li key={slot.start_at_utc}>
                      <button
                        type="button"
                        className="slot slot-free"
                        onClick={() => navigate(bookingLink(slot.start_at_ist))}
                      >
                        <span className="time">{time}</span>
                        <span>
                          Free<span className="visually-hidden">. Book this slot</span>
                        </span>
                      </button>
                    </li>
                  );
                }
                const appointment = slot.appointment;
                if (slot.state === "BOOKED" && appointment) {
                  return (
                    <li key={slot.start_at_utc}>
                      <button
                        type="button"
                        className="slot slot-booked"
                        aria-pressed={selectedId === appointment.id}
                        onClick={() => setSelectedId(appointment.id)}
                      >
                        <span className="time">{time}</span>
                        <span className="slot-name">
                          <Avatar name={appointment.patient_name} size="sm" />
                          {appointment.patient_name}
                        </span>
                        <span>
                          <StatusBadge status={appointment.status} />
                          {appointment.needs_attention ? " needs attention" : ""}
                        </span>
                      </button>
                    </li>
                  );
                }
                return (
                  <li key={slot.start_at_utc}>
                    <button type="button" className="slot slot-muted" disabled>
                      <span className="time">{time}</span>
                      <span>{STATE_TEXT[slot.state]}</span>
                    </button>
                  </li>
                );
              })}
            </ul>

            {doctorId !== null && <DayWaitlist doctorId={doctorId} date={date} />}

            {schedule.data.outside_availability.length > 0 && (
              <section aria-label="Booked outside the doctor's hours">
                <h2 className="attention-heading">Booked outside the doctor&apos;s hours</h2>
                {schedule.data.outside_availability.map((appointment) => (
                  <AppointmentCard key={appointment.id} appointment={appointment} />
                ))}
              </section>
            )}
          </section>

          <aside aria-label="Appointment details">
            <h2>Details</h2>
            {selectedId === null && (
              <DaySummary
                slots={schedule.data.slots}
                onBook={(start) => navigate(bookingLink(start))}
              />
            )}
            {selected.isPending && selectedId !== null && <Skeleton rows={3} />}
            {selected.error && <ErrorBanner error={selected.error} />}
            {selected.data && <AppointmentCard appointment={selected.data} />}
          </aside>
        </div>
      )}
    </div>
  );
}
