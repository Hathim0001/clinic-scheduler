import { useState } from "react";
import { useDeleteOverride, useOverrides } from "../../api/hooks";
import type { Doctor } from "../../api/types";
import { addDays, formatDayIST } from "../../lib/formatIST";
import { useToday } from "../../lib/useToday";
import { ErrorBanner, Skeleton } from "../common";
import { ConflictDialog } from "../ConflictDialog";
import { useConflictFlow } from "./useConflictFlow";

/** The next 90 days of overrides, each removable; removing one can also strand bookings. */
export function OverrideList({ doctor }: { doctor: Doctor }) {
  const today = useToday();
  const to = today ? addDays(today, 89) : "";
  const list = useOverrides(doctor.id, today, to);
  const remove = useDeleteOverride();
  const removeFlow = useConflictFlow();
  const [removing, setRemoving] = useState<string | null>(null);

  const runRemove = (day: string, acknowledge: boolean) => {
    setRemoving(day);
    remove.mutate(
      { doctorId: doctor.id, date: day, acknowledge },
      { onSuccess: removeFlow.clear, onError: removeFlow.intercept },
    );
  };

  return (
    <>
      <h3>Upcoming overrides (next 90 days)</h3>
      {list.isPending && today && <Skeleton rows={2} />}
      {list.error && <ErrorBanner error={list.error} />}
      {list.data && list.data.length === 0 && <p className="muted">None.</p>}
      <ul>
        {list.data?.map((override) => (
          <li key={override.date}>
            {formatDayIST(`${override.date}T12:00:00+05:30`)}:{" "}
            {override.windows.length === 0
              ? "leave"
              : override.windows.map((w) => `${w.start}–${w.end}`).join(", ")}
            {override.note ? ` (${override.note})` : ""}{" "}
            <button type="button" onClick={() => runRemove(override.date, false)}>
              Remove {override.date}
            </button>
          </li>
        ))}
      </ul>
      {remove.error && !removeFlow.conflict && <ErrorBanner error={remove.error} />}
      {removeFlow.conflict && removing && (
        <ConflictDialog
          message={removeFlow.conflict.message}
          appointments={removeFlow.conflict.appointments}
          busy={remove.isPending}
          onConfirm={() => runRemove(removing, true)}
          onCancel={removeFlow.clear}
        />
      )}
    </>
  );
}
