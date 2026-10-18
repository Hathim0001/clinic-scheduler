import { usePatientAppointments } from "../../api/hooks";
import { formatTimeIST, istDate } from "../../lib/formatIST";
import { Banner } from "../common";

interface Props {
  patientId: number | null;
  date: string;
  /** The appointment being moved, which is not "another" appointment on that day. */
  ignoreId?: number | null;
}

/**
 * A heads-up, not a rule: this patient already has a booked appointment on the chosen day. A
 * different time is allowed (only an overlap is refused), but a patient who forgot and rings again
 * is the usual cause, so the receptionist is told before booking a second visit.
 */
export function SameDayNotice({ patientId, date, ignoreId = null }: Props) {
  const history = usePatientAppointments(patientId, 100);
  if (patientId === null || date === "") return null;
  const others = (history.data?.items ?? []).filter(
    (a) => a.status === "BOOKED" && a.id !== ignoreId && istDate(a.start_at_ist) === date,
  );
  if (others.length === 0) return null;
  return (
    <Banner kind="warn">
      This patient already has {others.length === 1 ? "an appointment" : "appointments"} on this
      day: {others.map((a) => `${formatTimeIST(a.start_at_ist)} with ${a.doctor_name}`).join("; ")}.
      Check they are not booking the same visit twice.
    </Banner>
  );
}
