import { useState, type FormEvent } from "react";
import { useUpdateDoctor } from "../../api/hooks";
import type { Doctor } from "../../api/types";
import { Banner, ErrorBanner } from "../common";

export function DoctorDetails({ doctor }: { doctor: Doctor }) {
  const update = useUpdateDoctor();
  const [name, setName] = useState(doctor.name);
  const [speciality, setSpeciality] = useState(doctor.speciality);
  const [cap, setCap] = useState(String(doctor.daily_cap));
  const [slot, setSlot] = useState(String(doctor.slot_length_min));
  const [accepting, setAccepting] = useState(doctor.accepting_bookings);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({
      id: doctor.id,
      changes: {
        name,
        speciality,
        daily_cap: Number(cap),
        slot_length_min: Number(slot),
        accepting_bookings: accepting,
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
        <label className="check">
          <input
            type="checkbox"
            checked={accepting}
            onChange={(event) => setAccepting(event.target.checked)}
          />
          Taking new bookings
        </label>
        <button type="submit" className="primary" disabled={update.isPending}>
          Save details
        </button>
      </div>
      <p className="muted">
        The slot length cannot change while future bookings exist. Lowering the daily limit never
        cancels anything. Switching off &ldquo;Taking new bookings&rdquo; (leave, suspension) leaves
        existing appointments exactly as they are.
      </p>
      {update.error && <ErrorBanner error={update.error} />}
      {update.isSuccess && <Banner kind="success">Saved.</Banner>}
    </form>
  );
}

// ----------------------------------------------------------------------------- windows
