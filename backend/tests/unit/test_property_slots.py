"""T-P01: the rules agree with an independent restatement of them on random days.

The oracle below is written from the assignment text with integer minutes and plain sets. It imports
no rule function from `app.domain`, so a mistake would have to be made twice, in two different
styles, to slip through. Both `first_violation` (which slots are accepted) and `free_slots` (which
are offered) are compared with it on every minute of the day, which is what guarantees that the UI
never offers a slot the API then refuses (plan ADR-11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.domain.model import (
    AppointmentFacts,
    DepositStatus,
    DoctorFacts,
    PenaltyEvent,
    SlotContext,
    Status,
    Window,
)
from app.domain.penalties import deposit_status
from app.domain.slots import first_violation, free_slots

pytestmark = pytest.mark.unit

IST_OFFSET = 330  # minutes; India has no daylight saving time
ACTIVE = {Status.BOOKED, Status.COMPLETED, Status.NO_SHOW}  # these count toward the cap


@dataclass(frozen=True)
class Scenario:
    day: date
    ctx: SlotContext
    blocks: tuple[tuple[int, int], ...]
    odd_start: datetime  # a start with seconds or microseconds, which can never be on the grid


def ist_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC) - timedelta(minutes=IST_OFFSET)


def seconds(t: datetime) -> int:
    return int(t.timestamp())


def ist_day_number(t: datetime) -> int:
    """Whole days since 1970-01-01 on the India calendar."""
    return (seconds(t) // 60 + IST_OFFSET) // 1440


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    length = draw(st.sampled_from([15, 30]))
    cap = draw(st.integers(1, 6))

    # Zero to three working windows on the grid, sometimes touching each other.
    blocks: list[tuple[int, int]] = []
    cursor = draw(st.integers(7 * 60 // length, 11 * 60 // length)) * length
    for _ in range(draw(st.integers(0, 3))):
        size = draw(st.integers(2, 12)) * length
        if cursor + size > 21 * 60:
            break
        blocks.append((cursor, cursor + size))
        cursor += size + draw(st.integers(0, 4)) * length

    # Now is anywhere in 90 days, sometimes with seconds. The day under test is near it: from
    # yesterday to just beyond the 60 day horizon.
    now = datetime(2026, 10, 1, tzinfo=UTC) + timedelta(
        minutes=draw(st.integers(0, 90 * 24 * 60)), seconds=draw(st.sampled_from([0, 0, 0, 17]))
    )
    today = (now + timedelta(minutes=IST_OFFSET)).date()
    day = today + timedelta(days=draw(st.integers(-1, 62)))

    def start_on(day_shift: int, minute: int) -> datetime:
        return ist_midnight(day + timedelta(days=day_shift)) + timedelta(minutes=minute)

    # Appointments of the doctor with mixed statuses, on the day and its neighbours so that the day
    # boundary of the cap is exercised. Active ones never share a slot, as the database ensures.
    doctor_appts: list[AppointmentFacts] = []
    taken: set[tuple[int, int]] = set()
    for index in range(draw(st.integers(0, 8))):
        shift = draw(st.sampled_from([-1, 0, 0, 0, 1]))
        minute = draw(st.integers(0, 1440 // length - 1)) * length
        status = draw(st.sampled_from(list(Status)))
        if status in ACTIVE:
            if (shift, minute) in taken:
                continue
            taken.add((shift, minute))
        start = start_on(shift, minute)
        doctor_appts.append(
            AppointmentFacts(
                index, 1, 100 + index, start, start + timedelta(minutes=length), status
            )
        )

    # Other appointments of the patient, with other doctors: any quarter hour, 15 or 30 minutes.
    patient_appts: list[AppointmentFacts] = []
    for index in range(draw(st.integers(0, 3))):
        start = start_on(draw(st.sampled_from([-1, 0, 0, 0, 1])), draw(st.integers(0, 95)) * 15)
        minutes = draw(st.sampled_from([15, 30]))
        status = draw(st.sampled_from(list(Status)))
        patient_appts.append(
            AppointmentFacts(50 + index, 2, 7, start, start + timedelta(minutes=minutes), status)
        )

    odd_start = start_on(0, draw(st.integers(0, 1439))) + timedelta(
        seconds=draw(st.integers(0, 59)), microseconds=draw(st.sampled_from([0, 1, 500_000]))
    )
    if odd_start.second == 0 and odd_start.microsecond == 0:
        odd_start += timedelta(seconds=1)

    ctx = SlotContext(
        doctor=DoctorFacts(1, "Dr. Property", length, cap),
        windows=tuple(Window(a, b) for a, b in blocks),
        doctor_appts=tuple(doctor_appts),
        patient_appts=tuple(patient_appts),
        now=now,
    )
    return Scenario(day, ctx, tuple(blocks), odd_start)


def minutes_covered(appt: AppointmentFacts) -> set[int]:
    """The set of whole minutes (since the epoch) an appointment occupies."""
    return set(range(seconds(appt.start_at) // 60, seconds(appt.end_at) // 60))


class Oracle:
    """The plain-language rules, restated one fact at a time."""

    def __init__(self, scenario: Scenario) -> None:
        ctx = scenario.ctx
        self.ctx = ctx
        self.blocks = scenario.blocks
        self.length = ctx.doctor.slot_length_min
        self.cap = ctx.doctor.daily_cap
        self.doctor_active = [a for a in ctx.doctor_appts if a.status in ACTIVE]
        self.doctor_cover = [minutes_covered(a) for a in self.doctor_active]
        self.patient_cover = [minutes_covered(a) for a in ctx.patient_appts if a.status in ACTIVE]

    def accepts(self, start: datetime) -> bool:
        if start.microsecond or seconds(start) % 60:
            return False  # a start has whole minutes
        if seconds(start) <= seconds(self.ctx.now):
            return False  # not in the past, and not right now
        day = ist_day_number(start)
        if day - ist_day_number(self.ctx.now) > 60:
            return False  # at most 60 India calendar days ahead
        minute_of_day = (seconds(start) // 60 + IST_OFFSET) % 1440
        if minute_of_day % self.length:
            return False  # the grid is anchored at midnight
        if not any(a <= minute_of_day and minute_of_day + self.length <= b for a, b in self.blocks):
            return False  # inside one window, ending no later than it
        if sum(1 for a in self.doctor_active if ist_day_number(a.start_at) == day) >= self.cap:
            return False  # the daily cap, over active appointments only
        wanted = set(range(seconds(start) // 60, seconds(start) // 60 + self.length))
        if any(wanted & cover for cover in self.doctor_cover):
            return False  # the doctor is busy
        return not any(wanted & cover for cover in self.patient_cover)  # the patient is busy


@settings(
    max_examples=200,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(scenarios())
def test_offering_and_accepting_agree_with_the_oracle_on_every_minute(scenario: Scenario) -> None:
    oracle = Oracle(scenario)
    midnight = ist_midnight(scenario.day)

    accepted: list[datetime] = []
    for minute in range(24 * 60):
        start = midnight + timedelta(minutes=minute)
        violation = first_violation(start, scenario.ctx)
        assert (violation is None) == oracle.accepts(start), (start, violation)
        if violation is None:
            accepted.append(start)

    assert free_slots(scenario.day, scenario.ctx) == accepted  # same slots, in time order

    assert first_violation(scenario.odd_start, scenario.ctx) is not None
    assert not oracle.accepts(scenario.odd_start)


def deposit_oracle(
    events: list[PenaltyEvent], now: datetime
) -> tuple[bool, list[datetime], datetime | None]:
    """Strikes within 30 days, newest first; flagged from two, until 30 days after the 2nd."""
    window = timedelta(days=30)
    recent = sorted((e.at for e in events if now - window <= e.at <= now), reverse=True)
    if len(recent) < 2:
        return False, recent, None
    return True, recent, recent[1] + window


@settings(max_examples=300, deadline=None, derandomize=True)
@given(
    st.lists(
        st.tuples(
            st.integers(-2 * 24 * 3600, 45 * 24 * 3600),  # seconds before the base time
            st.sampled_from([Status.NO_SHOW, Status.LATE_CANCELLED]),
        ),
        max_size=6,
    ),
    st.integers(0, 30 * 24 * 3600),  # how far after the base time the check happens
)
def test_deposit_status_matches_a_plain_count_of_recent_strikes(
    ages: list[tuple[int, Status]], shift: int
) -> None:
    base = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    events = [
        PenaltyEvent(i, kind, base - timedelta(seconds=age)) for i, (age, kind) in enumerate(ages)
    ]
    now = base + timedelta(seconds=shift)

    status: DepositStatus = deposit_status(events, now)
    required, newest_first, until = deposit_oracle(events, now)

    assert status.required is required
    assert [e.at for e in status.reasons] == newest_first
    assert status.required_until == until
