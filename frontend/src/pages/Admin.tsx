import { useState } from "react";
import { useDoctors } from "../api/hooks";
import { DoctorDetails } from "../components/admin/DoctorDetails";
import { NeedsAttention } from "../components/admin/NeedsAttention";
import { NewDoctor } from "../components/admin/NewDoctor";
import { Overrides } from "../components/admin/Overrides";
import { RemoveDoctor } from "../components/admin/RemoveDoctor";
import { WeeklyHours } from "../components/admin/WeeklyHours";
import { ErrorBanner, Skeleton } from "../components/common";

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
            key={`${doctor.id}-${doctor.name}-${doctor.speciality}-${doctor.daily_cap}-${doctor.slot_length_min}-${doctor.accepting_bookings}`}
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
