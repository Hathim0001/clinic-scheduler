import { useAlternatives } from "../../api/hooks";
import type { Alternative } from "../../api/types";
import { formatIST, formatTimeIST, istDate } from "../../lib/formatIST";
import { ErrorBanner, Skeleton } from "../common";

interface Props {
  doctorId: number;
  date: string;
  patientId: number | undefined;
  slots: number;
  onChoose: (option: Alternative) => void;
}

/**
 * Shown when the chosen day has no time: the nearest times that the booking rules would accept
 * for this patient, with the same doctor first. Choosing one fills in the doctor, day and time;
 * the booking still goes through the normal checks.
 */
export function Alternatives({ doctorId, date, patientId, slots, onChoose }: Props) {
  const found = useAlternatives(doctorId, date, patientId, slots, true);

  if (found.isPending) return <Skeleton rows={1} />;
  if (found.error) return <ErrorBanner error={found.error} onRetry={() => void found.refetch()} />;
  if (!found.data || found.data.length === 0) {
    return <p className="muted">Nothing else is free in the next two weeks.</p>;
  }
  return (
    <section aria-label="Nearest available times">
      <h3>Nearest available times</h3>
      <ul className="slot-list">
        {found.data.map((option) => (
          <li key={`${option.doctor_id}-${option.start_at_utc}`}>
            <button
              type="button"
              className="slot slot-free"
              onClick={() => onChoose(option)}
              aria-label={`${option.doctor_name}, ${formatIST(option.start_at_ist)}`}
            >
              <span className="time">
                {formatTimeIST(option.start_at_ist)}–{formatTimeIST(option.end_at_ist)}
              </span>
              <span className="muted">
                {istDate(option.start_at_ist)}
                {option.same_doctor ? " · same doctor" : ` · ${option.doctor_name}`}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
