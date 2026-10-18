import { useState, type FormEvent } from "react";
import { useCreateDoctor } from "../../api/hooks";
import { ErrorBanner } from "../common";

export function NewDoctor({ onCreated }: { onCreated: (id: number) => void }) {
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
