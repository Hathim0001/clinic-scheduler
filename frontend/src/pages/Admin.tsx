import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import {
  useCreateDoctor,
  useDeleteDoctor,
  useDeleteOverride,
  useDoctors,
  useNeedsAttention,
  useOverrides,
  useSaveOverride,
  useSaveWeekly,
  useUpdateDoctor,
  useWeeklyWindows,
} from "../api/hooks";
import type { Doctor, TimeWindow, WeeklyWindow } from "../api/types";
import { AppointmentCard } from "../components/AppointmentCard";
import { Banner, ErrorBanner, Skeleton } from "../components/common";
import {
  ConflictDialog,
  conflictedAppointments,
  type ConflictedAppointment,
} from "../components/ConflictDialog";
import { addDays, formatDayIST } from "../lib/formatIST";
import { useToday } from "../lib/useToday";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const TIME_PATTERN = "([01][0-9]|2[0-3]):[0-5][0-9]|24:00";

interface Conflict {
  message: string;
  appointments: ConflictedAppointment[];
}

/**
 * A change to the hours that would leave booked appointments outside them is refused by the server
 * with the list. This turns that one error into a dialog; "Save anyway" sends the change again with
 * the acknowledgement. Every other error is shown as a normal banner.
 */
function useConflictFlow() {
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const intercept = (error: unknown) => {
    if (error instanceof ApiError && error.code === "AVAILABILITY_CONFLICTS") {
      setConflict({
        message: error.message,
        appointments: conflictedAppointments(error.details),
      });
    }
  };
  return { conflict, intercept, clear: () => setConflict(null) };
}

export default function Admin() {
  const doctors = useDoctors();
  const [pickedDoctor, setPickedDoctor] = useState<number | null>(null);
  const doctor = doctors.data?.find((d) => d.id === (pickedDoctor ?? doctors.data?.[0]?.id));

  return (
    <div>
      <h1>Doctors and availability</h1>
      {doctors.error && <ErrorBanner error={doctors.error} />}
      {doctors.isPending && <Skeleton rows={3} />}
      {doctors.data && (
        <div className="row">
          <label>
            Doctor
            <select
              value={doctor?.id ?? ""}
              onChange={(event) => setPickedDoctor(Number(event.target.value))}
            >
              {doctors.data.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {doctor && (
        <>
          <DoctorDetails
            key={`${doctor.id}-${doctor.name}-${doctor.speciality}-${doctor.daily_cap}-${doctor.slot_length_min}`}
            doctor={doctor}
          />
          <WeeklyHours doctor={doctor} />
          <Overrides doctor={doctor} />
          <RemoveDoctor doctor={doctor} onRemoved={() => setPickedDoctor(null)} />
        </>
      )}
      <NewDoctor onCreated={setPickedDoctor} />
      <NeedsAttention />
    </div>
  );
}

// ------------------------------------------------------------------------ add and remove

function NewDoctor({ onCreated }: { onCreated: (id: number) => void }) {
  const create = useCreateDoctor();
  const [name, setName] = useState("");
  const [speciality, setSpeciality] = useState("");
  const [cap, setCap] = useState("10");
  const [slot, setSlot] = useState("30");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      {
        name,
        speciality,
        daily_cap: Number(cap),
        slot_length_min: Number(slot),
      },
      {
        onSuccess: (created) => {
          setName("");
          setSpeciality("");
          onCreated(created.id);
        },
      },
    );
  };

  return (
    <form className="card" onSubmit={submit} aria-label="Add a doctor">
      <h2>Add a doctor</h2>
      <div className="row">
        <label>
          New doctor name
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
        </label>
        <label>
          New doctor speciality
          <input
            value={speciality}
            onChange={(event) => setSpeciality(event.target.value)}
            maxLength={100}
          />
        </label>
        <label>
          New doctor appointments per day
          <input
            type="number"
            min={1}
            max={96}
            value={cap}
            onChange={(event) => setCap(event.target.value)}
          />
        </label>
        <label>
          New doctor slot length
          <select value={slot} onChange={(event) => setSlot(event.target.value)}>
            <option value="15">15 minutes</option>
            <option value="30">30 minutes</option>
          </select>
        </label>
        <button
          type="submit"
          className="primary"
          disabled={create.isPending || name.trim() === "" || speciality.trim() === ""}
        >
          Add doctor
        </button>
      </div>
      <p className="muted">
        Set the weekly hours afterwards: a new doctor has no bookable times yet.
      </p>
      {create.error && <ErrorBanner error={create.error} />}
    </form>
  );
}

function RemoveDoctor({ doctor, onRemoved }: { doctor: Doctor; onRemoved: () => void }) {
  const remove = useDeleteDoctor();
  const [confirming, setConfirming] = useState(false);
  return (
    <section className="card" aria-label="Remove doctor">
      <h2>Remove this doctor</h2>
      <p className="muted">
        Only possible while the doctor has no appointments on record, past or future. Their hours
        and leave are deleted with them.
      </p>
      {!confirming ? (
        <button type="button" onClick={() => setConfirming(true)}>
          Remove {doctor.name}
        </button>
      ) : (
        <div className="actions">
          <button
            type="button"
            className="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(doctor.id, { onSuccess: onRemoved })}
          >
            Yes, remove {doctor.name}
          </button>
          <button type="button" onClick={() => setConfirming(false)}>
            Keep
          </button>
        </div>
      )}
      {remove.error && <ErrorBanner error={remove.error} />}
    </section>
  );
}

// ------------------------------------------------------------------------------- details

function DoctorDetails({ doctor }: { doctor: Doctor }) {
  const update = useUpdateDoctor();
  const [name, setName] = useState(doctor.name);
  const [speciality, setSpeciality] = useState(doctor.speciality);
  const [cap, setCap] = useState(String(doctor.daily_cap));
  const [slot, setSlot] = useState(String(doctor.slot_length_min));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({
      id: doctor.id,
      changes: {
        name,
        speciality,
        daily_cap: Number(cap),
        slot_length_min: Number(slot),
      },
    });
  };

  return (
    <form className="card" onSubmit={submit} aria-label="Doctor details">
      <h2>Details</h2>
      <div className="row">
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
        </label>
        <label>
          Speciality
          <input
            value={speciality}
            onChange={(event) => setSpeciality(event.target.value)}
            maxLength={100}
          />
        </label>
        <label>
          Appointments per day (limit)
          <input
            type="number"
            min={1}
            max={96}
            value={cap}
            onChange={(event) => setCap(event.target.value)}
          />
        </label>
        <label>
          Slot length
          <select value={slot} onChange={(event) => setSlot(event.target.value)}>
            <option value="15">15 minutes</option>
            <option value="30">30 minutes</option>
          </select>
        </label>
        <button type="submit" className="primary" disabled={update.isPending}>
          Save details
        </button>
      </div>
      <p className="muted">
        The slot length cannot change while future bookings exist. Lowering the daily limit never
        cancels anything.
      </p>
      {update.error && <ErrorBanner error={update.error} />}
      {update.isSuccess && <Banner kind="success">Saved.</Banner>}
    </form>
  );
}

// ----------------------------------------------------------------------------- windows

function WindowFields({
  label,
  window,
  onChange,
  onRemove,
}: {
  label: string;
  window: TimeWindow;
  onChange: (next: TimeWindow) => void;
  onRemove: () => void;
}) {
  return (
    <div className="row">
      <label>
        <span className="visually-hidden">{label} from</span>
        <input
          aria-label={`${label} from`}
          value={window.start}
          pattern={TIME_PATTERN}
          placeholder="09:00"
          size={6}
          onChange={(event) => onChange({ ...window, start: event.target.value })}
        />
      </label>
      <span>to</span>
      <label>
        <span className="visually-hidden">{label} to</span>
        <input
          aria-label={`${label} to`}
          value={window.end}
          pattern={TIME_PATTERN}
          placeholder="13:00"
          size={6}
          onChange={(event) => onChange({ ...window, end: event.target.value })}
        />
      </label>
      <button type="button" onClick={onRemove} aria-label={`Remove ${label}`}>
        Remove
      </button>
    </div>
  );
}

function WeeklyHours({ doctor }: { doctor: Doctor }) {
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
      {WEEKDAYS.map((dayName, weekday) => (
        <fieldset key={dayName}>
          <legend>{dayName}</legend>
          {rows.every((row) => row.weekday !== weekday) && (
            <span className="muted">Not working</span>
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
            onClick={() =>
              setRows((current) => [...current, { weekday, start: "09:00", end: "13:00" }])
            }
          >
            Add a window on {dayName}
          </button>
        </fieldset>
      ))}
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

// --------------------------------------------------------------------------- overrides

function Overrides({ doctor }: { doctor: Doctor }) {
  const today = useToday();
  const to = today ? addDays(today, 89) : "";
  const list = useOverrides(doctor.id, today, to);
  const save = useSaveOverride();
  const remove = useDeleteOverride();
  const saveFlow = useConflictFlow();
  const removeFlow = useConflictFlow();
  const [removing, setRemoving] = useState<string | null>(null);

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

  const runRemove = (day: string, acknowledge: boolean) => {
    setRemoving(day);
    remove.mutate(
      { doctorId: doctor.id, date: day, acknowledge },
      { onSuccess: removeFlow.clear, onError: removeFlow.intercept },
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (date) run(false);
  };

  return (
    <section className="card" aria-label="Date overrides">
      <h2>Leave and special hours</h2>
      <p className="muted">
        A date override replaces the weekly hours for that one date. Leave means not working. Hours
        on a day the doctor does not normally work add an extra working day.
      </p>
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
    </section>
  );
}

// -------------------------------------------------------------------- needs attention

function NeedsAttention() {
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
