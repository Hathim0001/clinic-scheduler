import { useState } from "react";
import { useSaveWeekly, useWeeklyWindows } from "../../api/hooks";
import type { Doctor, WeeklyWindow } from "../../api/types";
import { ConflictDialog } from "../ConflictDialog";
import { useConflictFlow } from "./useConflictFlow";
import { WindowFields } from "./WindowFields";
import { Banner, ErrorBanner, Skeleton } from "../common";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function WeeklyHours({ doctor }: { doctor: Doctor }) {
  const weekly = useWeeklyWindows(doctor.id);
  if (weekly.isPending) return <Skeleton rows={4} />;
  if (weekly.error) return <ErrorBanner error={weekly.error} />;
  return (
    <WeeklyEditor
      key={`${doctor.id}-${JSON.stringify(weekly.data.windows)}`}
      doctor={doctor}
      initial={weekly.data.windows}
    />
  );
}

function WeeklyEditor({ doctor, initial }: { doctor: Doctor; initial: WeeklyWindow[] }) {
  const save = useSaveWeekly();
  const flow = useConflictFlow();
  const [rows, setRows] = useState<WeeklyWindow[]>(initial);

  const run = (acknowledge: boolean) =>
    save.mutate(
      { doctorId: doctor.id, windows: rows, acknowledge },
      { onSuccess: flow.clear, onError: flow.intercept },
    );

  const change = (index: number, next: WeeklyWindow) =>
    setRows((current) => current.map((row, i) => (i === index ? next : row)));

  return (
    <section className="card" aria-label="Weekly hours">
      <h2>Weekly hours (IST)</h2>
      <p className="muted">
        Times are written HH:MM and must fall on the {doctor.slot_length_min}
        -minute grid.
      </p>
      <div className="week-grid">
        {WEEKDAYS.map((dayName, weekday) => (
          <fieldset key={dayName} className="day">
            <legend>{dayName}</legend>
            {rows.every((row) => row.weekday !== weekday) && (
              <span className="muted day-off">Not working</span>
            )}
            {rows.map((row, index) =>
              row.weekday !== weekday ? null : (
                <WindowFields
                  key={index}
                  label={`${dayName} window`}
                  window={row}
                  onChange={(next) => change(index, { ...next, weekday })}
                  onRemove={() => setRows((current) => current.filter((_, i) => i !== index))}
                />
              ),
            )}
            <button
              type="button"
              className="small"
              onClick={() =>
                setRows((current) => [...current, { weekday, start: "09:00", end: "13:00" }])
              }
            >
              Add a window on {dayName}
            </button>
          </fieldset>
        ))}
      </div>
      <div className="actions">
        <button
          type="button"
          className="primary"
          disabled={save.isPending}
          onClick={() => run(false)}
        >
          Save weekly hours
        </button>
      </div>
      {save.error && !flow.conflict && <ErrorBanner error={save.error} doctorName={doctor.name} />}
      {save.isSuccess && !flow.conflict && <Banner kind="success">Weekly hours saved.</Banner>}
      {flow.conflict && (
        <ConflictDialog
          message={flow.conflict.message}
          appointments={flow.conflict.appointments}
          busy={save.isPending}
          onConfirm={() => run(true)}
          onCancel={flow.clear}
        />
      )}
    </section>
  );
}
