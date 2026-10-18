import { useNeedsAttention } from "../../api/hooks";
import { AppointmentCard } from "../AppointmentCard";
import { ErrorBanner } from "../common";

export function NeedsAttention() {
  const attention = useNeedsAttention();
  return (
    <section aria-label="Needs attention">
      <h2 className="attention-heading">Appointments that need attention</h2>
      {attention.error && <ErrorBanner error={attention.error} />}
      {attention.data && attention.data.items.length === 0 && (
        <p className="muted">Every booked appointment is inside its doctor&apos;s hours.</p>
      )}
      {attention.data?.items.map((appointment) => (
        <AppointmentCard key={appointment.id} appointment={appointment} />
      ))}
    </section>
  );
}
