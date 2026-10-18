import type { Doctor } from "../../api/types";

interface Props {
  doctors: Doctor[] | undefined;
  doctorId: number | null;
  onDoctor: (id: number) => void;
  date: string;
  onDate: (date: string) => void;
  /** Shown only when booking: a reschedule keeps the visit's length. */
  visit?: { doctor: Doctor; slots: number; onSlots: (slots: number) => void };
}

export function DoctorDateFields({ doctors, doctorId, onDoctor, date, onDate, visit }: Props) {
  return (
    <div className="row">
      <label>
        Doctor
        <select value={doctorId ?? ""} onChange={(e) => onDoctor(Number(e.target.value))}>
          {doctors?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} ({d.speciality})
            </option>
          ))}
        </select>
      </label>
      <label>
        Date (India)
        <input type="date" value={date} onChange={(e) => onDate(e.target.value)} />
      </label>
      {visit && (
        <label>
          Length of the visit
          <select value={visit.slots} onChange={(e) => visit.onSlots(Number(e.target.value))}>
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n * visit.doctor.slot_length_min} minutes{n > 1 ? ` (${n} slots)` : ""}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
