"""Rules 1b, 2, 3 and 4 through the one shared predicate, and the free-slot list built on it."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.availability import resolve_windows
from app.domain.errors import ErrorCode
from app.domain.model import SlotContext, Status, WeeklyWindow, Window
from app.domain.slots import candidate_starts, first_violation, free_slots, is_on_grid, overlaps
from tests.helpers import appt_facts, doctor_facts, ist, slot_ctx

pytestmark = pytest.mark.unit

MONDAY = date(2026, 11, 2)
NOW = ist(2026, 11, 2, 8, 0)  # before the 09:00-13:00 window opens


def at(hour: int, minute: int = 0) -> datetime:
    return ist(2026, 11, 2, hour, minute)


@pytest.mark.parametrize(
    ("start", "length", "expected"),
    [
        (at(9, 0), 30, True),
        (at(9, 30), 30, True),
        (at(9, 15), 30, False),  # T-B01: a 30-minute doctor cannot be booked at 09:15
        (at(9, 15), 15, True),
        (at(9, 10), 15, False),
        (ist(2026, 11, 2, 9, 0, 30), 30, False),  # T-B13: 09:00:30 is not 09:00
        (ist(2026, 11, 2, 9, 0, 0, 500_000), 30, False),
        (datetime(2026, 11, 2, 3, 30, tzinfo=UTC), 30, True),  # T-B15: 03:30 UTC is 09:00 IST
        (datetime(2026, 11, 2, 3, 15, tzinfo=UTC), 30, False),  # 08:45 IST
    ],
    ids=[
        "09:00 on 30",
        "09:30 on 30",
        "09:15 on 30",
        "09:15 on 15",
        "09:10 on 15",
        "seconds",
        "microseconds",
        "UTC input on grid",
        "UTC input off grid",
    ],
)
def test_the_grid_is_anchored_at_ist_midnight(start: datetime, length: int, expected: bool) -> None:
    assert is_on_grid(start, length) is expected


@pytest.mark.parametrize(
    ("a_start", "a_end", "b_start", "b_end", "expected"),
    [
        (at(10), at(10, 30), at(10, 30), at(11), False),  # adjacent: half-open ranges
        (at(10), at(10, 30), at(10, 29), at(11), True),
        (at(10), at(11), at(10, 15), at(10, 30), True),  # one inside the other
        (at(10), at(10, 30), at(10), at(10, 30), True),  # identical
        (at(10), at(10, 30), at(9), at(10), False),
    ],
    ids=["adjacent", "one minute", "nested", "identical", "adjacent before"],
)
def test_overlap_is_half_open(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime, expected: bool
) -> None:
    assert overlaps(a_start, a_end, b_start, b_end) is expected


def test_a_free_slot_has_no_violation() -> None:
    assert first_violation(at(9), slot_ctx(now=NOW)) is None


def test_the_last_slot_ending_exactly_at_the_window_end_is_allowed() -> None:
    """T-B02"""
    assert first_violation(at(12, 30), slot_ctx(now=NOW)) is None


@pytest.mark.parametrize("start", [at(13), at(8, 30)], ids=["T-B03 after", "T-B04 before"])
def test_a_slot_outside_the_window_is_refused(start: datetime) -> None:
    assert first_violation(start, slot_ctx(now=NOW)) is ErrorCode.OUTSIDE_AVAILABILITY


def test_a_leave_day_has_no_available_slot() -> None:
    """T-B05"""
    assert first_violation(at(9), slot_ctx(now=NOW, windows=())) is ErrorCode.OUTSIDE_AVAILABILITY


def test_an_off_grid_start_is_refused() -> None:
    """T-B01"""
    assert first_violation(at(9, 15), slot_ctx(now=NOW)) is ErrorCode.OFF_GRID


def test_a_start_that_has_passed_is_refused() -> None:
    ctx = slot_ctx(now=at(10, 5))
    assert first_violation(at(10), ctx) is ErrorCode.BOOKING_IN_PAST


def test_a_start_more_than_sixty_days_away_is_refused() -> None:
    far = ist(2027, 1, 20, 9, 0)
    assert first_violation(far, slot_ctx(now=NOW)) is ErrorCode.BOOKING_TOO_FAR


def test_an_active_appointment_in_the_same_slot_takes_it() -> None:
    ctx = slot_ctx(now=NOW, doctor_appts=[appt_facts(at(10))])
    assert first_violation(at(10), ctx) is ErrorCode.SLOT_TAKEN
    assert first_violation(at(10, 30), ctx) is None  # the next slot is unaffected


@pytest.mark.parametrize("status", [Status.COMPLETED, Status.NO_SHOW])
def test_completed_and_no_show_appointments_still_occupy_their_slot(status: Status) -> None:
    ctx = slot_ctx(now=NOW, doctor_appts=[appt_facts(at(10), status=status)])
    assert first_violation(at(10), ctx) is ErrorCode.SLOT_TAKEN


@pytest.mark.parametrize("status", [Status.CANCELLED, Status.LATE_CANCELLED])
def test_a_cancelled_appointment_frees_its_slot(status: Status) -> None:
    ctx = slot_ctx(now=NOW, doctor_appts=[appt_facts(at(10), status=status)])
    assert first_violation(at(10), ctx) is None


def test_the_cap_ignores_cancelled_appointments() -> None:
    """T-B10: cap 3 with two active, one cancelled and one late-cancelled leaves room."""
    appts = [
        appt_facts(at(9)),
        appt_facts(at(9, 30)),
        appt_facts(at(10), status=Status.CANCELLED),
        appt_facts(at(10, 30), status=Status.LATE_CANCELLED),
    ]
    ctx = slot_ctx(now=NOW, doctor=doctor_facts(cap=3), doctor_appts=appts)
    assert first_violation(at(11), ctx) is None


def test_the_cap_counts_booked_completed_and_no_show() -> None:
    """T-B11: three active appointments of any active status fill a cap of 3."""
    appts = [
        appt_facts(at(9)),
        appt_facts(at(9, 30), status=Status.COMPLETED),
        appt_facts(at(10), status=Status.NO_SHOW),
    ]
    ctx = slot_ctx(now=NOW, doctor=doctor_facts(cap=3), doctor_appts=appts)
    assert first_violation(at(11), ctx) is ErrorCode.DAILY_CAP_REACHED


def test_the_cap_counts_only_the_day_of_the_slot() -> None:
    other_day = ist(2026, 11, 3, 9, 0)
    appts = [appt_facts(other_day), appt_facts(ist(2026, 11, 3, 9, 30))]
    ctx = slot_ctx(now=NOW, doctor=doctor_facts(cap=2), doctor_appts=appts)
    assert first_violation(at(11), ctx) is None


def test_a_patient_cannot_be_in_two_places_at_once() -> None:
    """T-B08: the patient's appointment with another doctor overlaps this slot."""
    elsewhere = appt_facts(at(10), doctor=2, patient=7)
    ctx = slot_ctx(now=NOW, patient_appts=[elsewhere])
    assert first_violation(at(10), ctx) is ErrorCode.PATIENT_OVERLAP


def test_a_patients_overlap_may_be_partial() -> None:
    """A 30-minute booking at 10:00 overlaps the patient's 15-minute visit at 10:15."""
    elsewhere = appt_facts(at(10, 15), doctor=2, patient=7, minutes=15)
    ctx = slot_ctx(now=NOW, patient_appts=[elsewhere])
    assert first_violation(at(10), ctx) is ErrorCode.PATIENT_OVERLAP


def test_back_to_back_appointments_for_a_patient_are_fine() -> None:
    before = appt_facts(at(9, 30), doctor=2, patient=7)
    after = appt_facts(at(10, 30), doctor=2, patient=7)
    ctx = slot_ctx(now=NOW, patient_appts=[before, after])
    assert first_violation(at(10), ctx) is None


def test_a_cancelled_appointment_of_the_patient_is_ignored() -> None:
    cancelled = appt_facts(at(10), doctor=2, patient=7, status=Status.CANCELLED)
    assert first_violation(at(10), slot_ctx(now=NOW, patient_appts=[cancelled])) is None


@pytest.mark.parametrize(
    ("start", "ctx", "expected"),
    [
        pytest.param(
            at(9, 15),
            slot_ctx(now=at(10)),
            ErrorCode.BOOKING_IN_PAST,
            id="past beats off-grid",
        ),
        pytest.param(
            at(13, 15),
            slot_ctx(now=NOW),
            ErrorCode.OFF_GRID,
            id="off-grid beats outside availability",
        ),
        pytest.param(
            at(13),
            slot_ctx(now=NOW, doctor=doctor_facts(cap=1), doctor_appts=[appt_facts(at(9))]),
            ErrorCode.OUTSIDE_AVAILABILITY,
            id="outside availability beats the cap",
        ),
        pytest.param(
            at(9),
            slot_ctx(now=NOW, doctor=doctor_facts(cap=1), doctor_appts=[appt_facts(at(9))]),
            ErrorCode.DAILY_CAP_REACHED,
            id="the cap beats a taken slot",
        ),
        pytest.param(
            at(9),
            slot_ctx(
                now=NOW,
                doctor_appts=[appt_facts(at(9), patient=8)],
                patient_appts=[appt_facts(at(9), doctor=2, patient=7)],
            ),
            ErrorCode.SLOT_TAKEN,
            id="a taken slot beats the patient's own overlap",
        ),
    ],
)
def test_rules_are_checked_in_a_fixed_order(
    start: datetime, ctx: SlotContext, expected: ErrorCode
) -> None:
    """The order is documented in the plan (section 21.7), so errors are predictable."""
    assert first_violation(start, ctx) is expected


def test_override_beats_the_weekly_pattern_on_both_sides() -> None:
    """T-B14: weekly 10:00-14:00 but an override of 11:00-13:00 for this Monday."""
    weekly = [WeeklyWindow(0, 600, 840)]
    windows, _ = resolve_windows(MONDAY, weekly, [Window(660, 780)])
    ctx = SlotContext(
        doctor=doctor_facts(),
        windows=windows,
        doctor_appts=(),
        patient_appts=(),
        now=ist(2026, 11, 2, 9, 0),
    )
    assert first_violation(at(10, 30), ctx) is ErrorCode.OUTSIDE_AVAILABILITY  # weekly allows it
    assert first_violation(at(13, 30), ctx) is ErrorCode.OUTSIDE_AVAILABILITY  # weekly allows it
    assert first_violation(at(11), ctx) is None


def test_candidate_starts_follow_the_windows_in_time_order() -> None:
    windows = (Window(540, 600), Window(1020, 1050))
    starts = list(candidate_starts(MONDAY, windows, 30))
    assert starts == [at(9), at(9, 30), at(17)]


def test_candidate_starts_skip_a_partial_slot_at_the_end_of_a_window() -> None:
    assert list(candidate_starts(MONDAY, (Window(540, 585),), 30)) == [at(9)]


def test_free_slots_for_the_worked_example_in_the_plan() -> None:
    """Dr. Menon, 30 minutes, cap 6. Override 11:00-13:00, a booking at 11:30, now 10:05."""
    ctx = slot_ctx(
        now=ist(2026, 11, 2, 10, 5),
        doctor=doctor_facts(slot=30, cap=6),
        windows=[(660, 780)],
        doctor_appts=[appt_facts(at(11, 30))],
    )
    assert free_slots(MONDAY, ctx) == [at(11), at(12), at(12, 30)]
    assert first_violation(at(10), ctx) is ErrorCode.BOOKING_IN_PAST
    assert first_violation(at(10, 30), ctx) is ErrorCode.OUTSIDE_AVAILABILITY
    assert first_violation(at(11, 15), ctx) is ErrorCode.OFF_GRID
    assert first_violation(at(11, 30), ctx) is ErrorCode.SLOT_TAKEN


def test_free_slots_drop_slots_that_have_already_started() -> None:
    ctx = slot_ctx(now=at(10, 45))
    assert free_slots(MONDAY, ctx) == [at(11), at(11, 30), at(12), at(12, 30)]


def test_free_slots_are_empty_on_a_leave_day() -> None:
    assert free_slots(MONDAY, slot_ctx(now=NOW, windows=())) == []


def test_free_slots_are_empty_once_the_cap_is_reached() -> None:
    appts = [appt_facts(at(9)), appt_facts(at(9, 30))]
    ctx = slot_ctx(now=NOW, doctor=doctor_facts(cap=2), doctor_appts=appts)
    assert free_slots(MONDAY, ctx) == []


def test_free_slots_skip_times_the_patient_is_already_busy() -> None:
    busy = appt_facts(at(10), doctor=2, patient=7)
    ctx = slot_ctx(now=NOW, patient_appts=[busy])
    assert at(10) not in free_slots(MONDAY, ctx)
    assert at(9, 30) in free_slots(MONDAY, ctx)


def test_every_free_slot_passes_the_booking_check() -> None:
    """The point of one predicate: whatever is offered can be booked."""
    appts = [appt_facts(at(9, 30)), appt_facts(at(11), status=Status.NO_SHOW)]
    ctx = slot_ctx(now=at(9, 10), doctor=doctor_facts(cap=5), doctor_appts=appts)
    offered = free_slots(MONDAY, ctx)
    assert offered
    assert all(first_violation(start, ctx) is None for start in offered)
    assert timedelta(0) < offered[0] - ctx.now
