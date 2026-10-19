"""Reminders: queued once per visit and kind, only when they still make sense, and withdrawn when
the visit is cancelled, moved or over."""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest

from app.domain.model import CancelledBy
from app.services.notification_service import NotificationService
from app.services.policy_service import PolicyService
from app.services.views import BookCommand
from tests.integration.conftest import NOW, Clinic, at

pytestmark = pytest.mark.integration


class Recorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, body: str, kind: str) -> None:
        self.sent.append((to, body, kind))


def service(clinic: Clinic) -> NotificationService:
    return NotificationService(clinic.factory)


def reminders(clinic: Clinic):  # type: ignore[no-untyped-def]
    return [m for m in service(clinic).list(None, 100, 0).items if m.kind.startswith("REMINDER")]


def book_wednesday_ten(clinic: Clinic, patient: int | None = None) -> int:
    """Booked on Monday 08:00 for Wednesday 10:00: 50 hours ahead, so both reminders apply."""
    clinic.patients.record_consent(patient or clinic.asha, NOW)
    booked = clinic.booking.book(
        BookCommand(clinic.rao, patient or clinic.asha, at(10, day=4), "Check-up"), NOW
    )
    return booked.id


def test_nothing_is_queued_before_the_first_reminder_is_due(clinic: Clinic) -> None:
    book_wednesday_ten(clinic)
    assert service(clinic).schedule_reminders(at(9, day=3)) == 0  # 25 hours before
    assert reminders(clinic) == []


def test_the_first_reminder_is_queued_once_it_is_due_and_never_twice(clinic: Clinic) -> None:
    appointment_id = book_wednesday_ten(clinic)
    assert service(clinic).schedule_reminders(at(10, 30, day=3)) == 1  # 23.5 hours before
    assert service(clinic).schedule_reminders(at(11, day=3)) == 0
    (message,) = reminders(clinic)
    assert (message.kind, message.status, message.appointment_id) == (
        "REMINDER_FIRST",
        "PENDING",
        appointment_id,
    )
    assert "Dr. Rao" in message.body
    assert "04 Nov 2026, 10:00" in message.body
    assert "cannot come" in message.body


def test_the_second_reminder_follows_the_first(clinic: Clinic) -> None:
    book_wednesday_ten(clinic)
    service(clinic).schedule_reminders(at(10, 30, day=3))
    assert service(clinic).schedule_reminders(at(8, 30, day=4)) == 1  # 90 minutes before
    kinds = sorted(m.kind for m in reminders(clinic))
    assert kinds == ["REMINDER_FIRST", "REMINDER_SECOND"]


def test_a_visit_booked_inside_the_first_period_gets_only_the_second_reminder(
    clinic: Clinic,
) -> None:
    clinic.patients.record_consent(clinic.asha, NOW)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(10), "x"), NOW)  # same morning
    assert service(clinic).schedule_reminders(NOW + timedelta(seconds=1)) == 1
    (message,) = reminders(clinic)
    assert message.kind == "REMINDER_SECOND"


def test_a_visit_booked_less_than_the_second_period_ahead_gets_no_reminder(
    clinic: Clinic,
) -> None:
    clinic.patients.record_consent(clinic.asha, NOW)
    nine_fifty = NOW + timedelta(hours=1, minutes=50)
    clinic.booking.book(BookCommand(clinic.rao, clinic.asha, at(11), "x"), nine_fifty)
    assert service(clinic).schedule_reminders(nine_fifty + timedelta(minutes=5)) == 0


def test_a_patient_without_consent_gets_a_skipped_reminder_that_says_to_phone(
    clinic: Clinic,
) -> None:
    clinic.booking.book(BookCommand(clinic.rao, clinic.ravi, at(10, day=4), "x"), NOW)
    service(clinic).schedule_reminders(at(10, 30, day=3))
    (message,) = reminders(clinic)
    assert message.status == "SKIPPED"
    assert message.last_error is not None
    assert "phone" in message.last_error


def test_a_cancelled_visit_gets_no_reminder_and_a_waiting_one_is_withdrawn(clinic: Clinic) -> None:
    appointment_id = book_wednesday_ten(clinic)
    service(clinic).schedule_reminders(at(10, 30, day=3))
    (waiting,) = reminders(clinic)
    assert waiting.status == "PENDING"

    clinic.booking.cancel(appointment_id, CancelledBy.PATIENT, at(11, day=3))
    service(clinic).schedule_reminders(at(8, 30, day=4))

    (after,) = reminders(clinic)  # no second reminder was added for a cancelled visit
    assert after.status == "SKIPPED"
    assert "no longer ahead" in (after.last_error or "")


def test_a_moved_visit_is_reminded_at_its_new_time_not_its_old_one(clinic: Clinic) -> None:
    appointment_id = book_wednesday_ten(clinic)
    moved = clinic.booking.reschedule(appointment_id, at(10, day=5), None, None, NOW)
    service(clinic).schedule_reminders(at(10, 30, day=3))  # 23.5 hours before the OLD time
    assert reminders(clinic) == []
    assert service(clinic).schedule_reminders(at(10, 30, day=4)) == 1
    (message,) = reminders(clinic)
    assert message.appointment_id == moved.new.id
    assert "05 Nov 2026, 10:00" in message.body


def test_a_pending_reminder_for_a_visit_that_has_begun_is_not_sent(clinic: Clinic) -> None:
    book_wednesday_ten(clinic)
    service(clinic).schedule_reminders(at(10, 30, day=3))
    service(clinic).schedule_reminders(at(10, 5, day=4))  # the visit began five minutes ago
    (message,) = reminders(clinic)
    assert message.status == "SKIPPED"


def test_the_clinics_reminder_hours_are_used(clinic: Clinic) -> None:
    PolicyService(clinic.factory).update({"reminder_first_hours": 48}, NOW)
    book_wednesday_ten(clinic)
    assert service(clinic).schedule_reminders(at(9, day=2)) == 0  # 49 hours: not yet
    assert service(clinic).schedule_reminders(at(11, day=2)) == 1  # 47 hours: first is due
    (message,) = reminders(clinic)
    assert message.kind == "REMINDER_FIRST"


def test_a_reminder_can_be_switched_off(clinic: Clinic) -> None:
    PolicyService(clinic.factory).update(
        {"reminder_first_hours": 0, "reminder_second_hours": 0}, NOW
    )
    book_wednesday_ten(clinic)
    assert service(clinic).schedule_reminders(at(10, 30, day=3)) == 0
    assert service(clinic).schedule_reminders(at(9, day=4)) == 0


def test_two_servers_scheduling_at_the_same_moment_queue_one_reminder(clinic: Clinic) -> None:
    book_wednesday_ten(clinic)
    barrier = threading.Barrier(4)
    totals: list[int] = []

    def run() -> None:
        barrier.wait()
        totals.append(service(clinic).schedule_reminders(at(10, 30, day=3)))

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(totals) == 1
    assert len(reminders(clinic)) == 1


def test_a_due_reminder_is_sent_through_the_gateway_with_its_kind(clinic: Clinic) -> None:
    book_wednesday_ten(clinic)
    when = at(10, 30, day=3)
    service(clinic).schedule_reminders(when)
    gateway = Recorder()
    assert service(clinic).dispatch(gateway, when) == 2  # the booking confirmation and the reminder
    assert sorted(kind for _, _, kind in gateway.sent) == ["APPOINTMENT_BOOKED", "REMINDER_FIRST"]
    assert service(clinic).summary()["reminders_sent"] == 1


def test_the_summary_counts_each_status(clinic: Clinic) -> None:
    book_wednesday_ten(clinic)
    counts = service(clinic).summary()
    assert counts["PENDING"] == 1
    assert counts["SENT"] == counts["FAILED"] == counts["SKIPPED"] == 0
    assert counts["reminders_sent"] == 0
