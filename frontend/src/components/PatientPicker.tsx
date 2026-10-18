import { useState, type FormEvent } from "react";
import { usePatientSearch, useCreatePatient } from "../api/hooks";
import type { Patient } from "../api/types";
import { ApiError } from "../api/client";
import { Banner, ErrorBanner, Skeleton } from "./common";

interface Props {
  onSelect: (patient: Patient) => void;
  selectedId?: number | null;
}

const LOOKS_LIKE_PHONE = /^[\d\s()+.-]{3,}$/;

/** Find a patient by phone or by the start of the name, or register a new one on the spot. */
export function PatientPicker({ onSelect, selectedId = null }: Props) {
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  const [registering, setRegistering] = useState(false);

  const trimmed = term.trim();
  const isPhone = LOOKS_LIKE_PHONE.test(trimmed);
  const search = usePatientSearch(isPhone ? { phone: trimmed } : trimmed ? { q: trimmed } : {});

  const submit = (event: { preventDefault: () => void }) => {
    event.preventDefault();
    setTerm(text);
    setRegistering(false);
  };

  return (
    <div>
      {/* A div, not a form: this picker sits inside the booking form and forms cannot nest. */}
      <div className="row" role="search">
        <label>
          Find a patient by phone or name
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit(event);
            }}
            maxLength={100}
          />
        </label>
        <button type="button" onClick={submit} disabled={!text.trim()}>
          Search
        </button>
        <button type="button" onClick={() => setRegistering(true)}>
          New patient
        </button>
      </div>

      {search.isPending && trimmed && <Skeleton rows={2} />}
      {search.error && <ErrorBanner error={search.error} onRetry={() => void search.refetch()} />}
      {search.data && (
        <ul aria-label="Matching patients">
          {search.data.items.map((patient) => (
            <li key={patient.id}>
              <button
                type="button"
                className="link"
                aria-pressed={patient.id === selectedId}
                onClick={() => onSelect(patient)}
              >
                {patient.name}
              </button>{" "}
              <span className="muted">{patient.phone}</span>
            </li>
          ))}
          {search.data.items.length === 0 && (
            <li className="muted">
              No patient found.{" "}
              <button type="button" className="link" onClick={() => setRegistering(true)}>
                Register a new patient
              </button>
            </li>
          )}
        </ul>
      )}

      {registering && (
        <NewPatientForm
          initial={isPhone ? { phone: trimmed } : { name: trimmed }}
          onCreated={(patient) => {
            setRegistering(false);
            onSelect(patient);
          }}
          onCancel={() => setRegistering(false)}
        />
      )}
    </div>
  );
}

function NewPatientForm({
  initial,
  onCreated,
  onCancel,
}: {
  initial: { name?: string; phone?: string };
  onCreated: (patient: Patient) => void;
  onCancel: () => void;
}) {
  const create = useCreatePatient();
  const [name, setName] = useState(initial.name ?? "");
  const [phone, setPhone] = useState(initial.phone ?? "");
  const [birth, setBirth] = useState("");

  const register = (allowDuplicate: boolean) =>
    create.mutate(
      { name, phone, date_of_birth: birth, ...(allowDuplicate ? { allow_duplicate: true } : {}) },
      { onSuccess: onCreated },
    );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    register(false);
  };

  const duplicates =
    create.error instanceof ApiError && create.error.code === "POSSIBLE_DUPLICATE"
      ? ((create.error.details.candidates as {
          patient_id: number;
          name: string;
          phone: string;
        }[]) ?? [])
      : null;

  return (
    <form className="card" onSubmit={submit} aria-label="New patient">
      <h2>New patient</h2>
      <div className="row">
        <label>
          Name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={100}
          />
        </label>
        <label>
          Phone
          <input
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            required
            inputMode="tel"
            placeholder="98765 43210"
            maxLength={40}
          />
        </label>
        <label>
          Date of birth
          <input
            type="date"
            value={birth}
            onChange={(event) => setBirth(event.target.value)}
            required
            min="1900-01-01"
          />
        </label>
      </div>
      {duplicates ? (
        <Banner kind="warn">
          Someone with the same name and date of birth is already registered:
          <ul>
            {duplicates.map((match) => (
              <li key={match.patient_id}>
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    onCreated({
                      id: match.patient_id,
                      name: match.name,
                      phone: match.phone,
                    } as Patient)
                  }
                >
                  Use {match.name}
                </button>{" "}
                <span className="muted">{match.phone}</span>
              </li>
            ))}
          </ul>
          If this really is a different person, register them anyway.
        </Banner>
      ) : (
        create.error && <ErrorBanner error={create.error} />
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={create.isPending}>
          Register patient
        </button>
        {duplicates && (
          <button type="button" disabled={create.isPending} onClick={() => register(true)}>
            Register anyway
          </button>
        )}
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
