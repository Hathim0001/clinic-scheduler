import type { ScheduleSlot } from "../api/types";
import { formatTimeIST } from "../lib/formatIST";

interface Props {
  slots: ScheduleSlot[];
  onBook: (startIst: string) => void;
}

/**
 * What the day looks like at a glance, shown where the details go until a booking is selected: how
 * many slots are booked and free, and the next free time with a one-press way to book it.
 */
export function DaySummary({ slots, onBook }: Props) {
  const booked = slots.filter((s) => s.state === "BOOKED").length;
  const free = slots.filter((s) => s.state === "FREE");
  const next = free[0];

  return (
    <div className="day-summary">
      <p className="day-figures">
        <span>
          <strong>{booked}</strong> booked
        </span>
        <span>
          <strong>{free.length}</strong> free
        </span>
      </p>
      {next ? (
        <p>
          Next free time is {formatTimeIST(next.start_at_ist)}–{formatTimeIST(next.end_at_ist)}.{" "}
          <button type="button" className="link" onClick={() => onBook(next.start_at_ist)}>
            Book it
          </button>
        </p>
      ) : (
        <p className="muted">Nothing is free on this day. Try the next day or another doctor.</p>
      )}
      <p className="muted">Select a booked slot to see the details.</p>
    </div>
  );
}
