"""The nearest bookable times when the one that was asked for is not available.

A refusal ("that day is full", "the doctor is on leave") is where a receptionist loses the call.
This looks for the next free starts with the same doctor, and for the same day with other doctors
who take bookings. Every probe goes through `AvailabilityService.free_slots`, so an alternative is
offered only when the booking rules would accept it for this patient and visit length. It only
reads; booking an alternative goes through the normal booking path and its checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.services.availability_service import AvailabilityService
from app.services.doctor_service import DoctorService
from app.services.views import DoctorView

SAME_DOCTOR_DAYS = 14  # how far ahead to look for the same doctor
OTHER_DOCTOR_DAYS = 3  # other doctors: the day asked for and the next few
DEFAULT_LIMIT = 6


@dataclass(frozen=True, slots=True)
class Alternative:
    doctor_id: int
    doctor_name: str
    speciality: str
    start_at: datetime
    duration_min: int
    same_doctor: bool


class AlternativesService:
    def __init__(self, availability: AvailabilityService, doctors: DoctorService) -> None:
        self._availability = availability
        self._doctors = doctors

    def nearest(
        self,
        doctor_id: int,
        day: date,
        patient_id: int | None,
        now: datetime,
        slots: int = 1,
        limit: int = DEFAULT_LIMIT,
    ) -> list[Alternative]:
        """Up to `limit` options, the same doctor's next days first, then other doctors.

        Each (doctor, day) contributes its first free start, so the list spreads over days instead
        of listing every slot of one morning.
        """
        asked = self._doctors.get(doctor_id)
        same = self._first_starts([asked], day, SAME_DOCTOR_DAYS, patient_id, now, slots, True)
        others = [d for d in self._doctors.list() if d.id != asked.id and d.accepting_bookings]
        others.sort(key=lambda d: (d.speciality != asked.speciality, d.name))
        elsewhere = self._first_starts(
            others, day, OTHER_DOCTOR_DAYS, patient_id, now, slots, False
        )
        # Half the list is the patient's own doctor on later days, the rest other doctors, so a
        # busy doctor's next fortnight cannot crowd out a free colleague. Unused room is refilled.
        own = same[: (limit + 1) // 2]
        rest = elsewhere[: limit - len(own)]
        own = same[: limit - len(rest)]
        return sorted(own + rest, key=lambda a: (not a.same_doctor, a.start_at))

    def _first_starts(
        self,
        doctors: list[DoctorView],
        first_day: date,
        days: int,
        patient_id: int | None,
        now: datetime,
        slots: int,
        same_doctor: bool,
    ) -> list[Alternative]:
        found: list[Alternative] = []
        for doctor in doctors:
            for offset in range(days):
                view = self._availability.free_slots(
                    doctor.id, first_day + timedelta(days=offset), patient_id, now, slots
                )
                if view.slots:
                    found.append(
                        Alternative(
                            doctor_id=doctor.id,
                            doctor_name=doctor.name,
                            speciality=doctor.speciality,
                            start_at=view.slots[0],
                            duration_min=view.duration_min,
                            same_doctor=same_doctor,
                        )
                    )
        return found
