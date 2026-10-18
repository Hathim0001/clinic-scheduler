import type { SlotsResponse } from "../../api/types";
import { REASON_TEXT } from "../../lib/errors";
import { formatDayIST, formatTimeIST } from "../../lib/formatIST";
import { Banner, ErrorBanner, Skeleton } from "../common";

interface Props {
  slots: {
    data: SlotsResponse | undefined;
    error: Error | null;
    isPending: boolean;
    refetch: () => Promise<unknown>;
  };
  /** The starts to show: empty when the visit cannot be placed with this doctor at all. */
  offered: SlotsResponse["slots"];
  start: string | null;
  onPick: (startIst: string) => void;
  doctorName?: string;
  forPatient: boolean;
  loading: boolean;
}

/** The "Time" card: the bookable starts for the chosen doctor and day, and why there are none. */
export function SlotPicker({
  slots,
  offered,
  start,
  onPick,
  doctorName,
  forPatient,
  loading,
}: Props) {
  return (
    <>
      {slots.isPending && loading && <Skeleton rows={2} />}
      {slots.error && (
        <ErrorBanner
          error={slots.error}
          doctorName={doctorName}
          onRetry={() => void slots.refetch()}
        />
      )}
      {slots.data && offered.length === 0 && (
        <Banner kind="info">
          {slots.data.unavailable_reason
            ? REASON_TEXT[slots.data.unavailable_reason]
            : "No free times."}{" "}
          Try another date or doctor.
        </Banner>
      )}
      {slots.data && offered.length > 0 && (
        <>
          <p className="muted">
            {formatDayIST(`${slots.data.date}T12:00:00+05:30`)}, {slots.data.slot_length_min}
            -minute slots. Only bookable times are listed{forPatient ? " for this patient" : ""}.
          </p>
          <ul className="slot-list">
            {offered.map((slot) => (
              <li key={slot.start_at_utc}>
                <button
                  type="button"
                  className="slot slot-free"
                  aria-pressed={start === slot.start_at_ist}
                  onClick={() => onPick(slot.start_at_ist)}
                >
                  <span className="time">
                    {formatTimeIST(slot.start_at_ist)}–{formatTimeIST(slot.end_at_ist)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
