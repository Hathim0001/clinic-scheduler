import { useState, type FormEvent } from "react";
import { useSaveOverride } from "../../api/hooks";
import type { Doctor, TimeWindow } from "../../api/types";
import { Banner, ErrorBanner } from "../common";
import { ConflictDialog } from "../ConflictDialog";
import { useConflictFlow } from "./useConflictFlow";
import { WindowFields } from "./WindowFields";

/** Add a leave day or special hours for one date; a change that strands bookings asks first. */
export function OverrideForm({ doctor }: { doctor: Doctor }) {
  const save = useSaveOverride();
  const saveFlow = useConflictFlow();
  const [date, setDate] = useState("");
  const [mode, setMode] = useState<"leave" | "hours">("leave");
  const [windows, setWindows] = useState<TimeWindow[]>([{ start: "10:00", end: "12:00" }]);
  const [note, setNote] = useState("");

  const run = (acknowledge: boolean) =>
    save.mutate(
      {
        doctorId: doctor.id,
        date,
        windows: mode === "leave" ? [] : windows,
        note,
        acknowledge,
      },
      { onSuccess: saveFlow.clear, onError: saveFlow.intercept },
    );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (date) run(false);
  };

  return (
    <>
      <form onSubmit={submit}>
        <div className="row">
          <label>
            Date
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              required
            />
          </label>
          <label className="check">
            <input
              type="radio"
              name="mode"
              checked={mode === "leave"}
              onChange={() => setMode("leave")}
            />
            Leave (not working)
          </label>
          <label className="check">
            <input
              type="radio"
              name="mode"
              checked={mode === "hours"}
              onChange={() => setMode("hours")}
            />
            Special hours
          </label>
          <label>
            Note
            <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={200} />
          </label>
        </div>
        {mode === "hours" && (
          <div>
            {windows.map((window, index) => (
              <WindowFields
                key={index}
                label={`Override window ${index + 1}`}
                window={window}
                onChange={(next) =>
                  setWindows((current) => current.map((w, i) => (i === index ? next : w)))
                }
                onRemove={() => setWindows((current) => current.filter((_, i) => i !== index))}
              />
            ))}
            <button
              type="button"
              onClick={() => setWindows((c) => [...c, { start: "09:00", end: "13:00" }])}
            >
              Add a window
            </button>
          </div>
        )}
        <div className="actions">
          <button type="submit" className="primary" disabled={save.isPending || !date}>
            Save override
          </button>
        </div>
      </form>
      {save.error && !saveFlow.conflict && (
        <ErrorBanner error={save.error} doctorName={doctor.name} />
      )}
      {save.isSuccess && !saveFlow.conflict && <Banner kind="success">Override saved.</Banner>}
      {saveFlow.conflict && (
        <ConflictDialog
          message={saveFlow.conflict.message}
          appointments={saveFlow.conflict.appointments}
          busy={save.isPending}
          onConfirm={() => run(true)}
          onCancel={saveFlow.clear}
        />
      )}
    </>
  );
}
