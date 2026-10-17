"""Calendar export (iCalendar, RFC 5545): one event per appointment, so a patient can add a visit to
a phone calendar. Instants are written in UTC, which every calendar app converts to local time."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.domain.timeutil import utc_iso
from app.services.views import AppointmentView

PRODID = "-//Clinic Scheduler//EN"


def _compact(instant: datetime) -> str:
    return utc_iso(instant).replace("-", "").replace(":", "")  # 20261102T043000Z


def _escape(text: str) -> str:
    cleaned = text.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
    return cleaned.replace("\r\n", "\n").replace("\n", "\n").replace("\r", "\n")


def _fold(line: str) -> list[str]:
    """Lines are at most 75 octets; a longer one continues on the next line after a space."""
    raw, parts = line.encode("utf-8"), []
    while len(raw) > 75:
        cut = 75
        while raw[cut] & 0xC0 == 0x80:  # do not split a multi-byte character
            cut -= 1
        parts.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    parts.append(raw.decode("utf-8"))
    return parts


def calendar_text(appointments: Sequence[AppointmentView], stamp: datetime) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN"]
    for a in appointments:
        lines += [
            "BEGIN:VEVENT",
            f"UID:appointment-{a.id}@clinic-scheduler",
            f"DTSTAMP:{_compact(stamp)}",
            f"DTSTART:{_compact(a.start_at)}",
            f"DTEND:{_compact(a.end_at)}",
            f"SUMMARY:{_escape('Appointment with ' + a.doctor_name)}",
            f"DESCRIPTION:{_escape(a.reason)}",
            "STATUS:CONFIRMED" if a.status.value == "BOOKED" else "STATUS:CANCELLED",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"
