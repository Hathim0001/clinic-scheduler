"""Parsing and bounds for values that arrive as text: instants, dates, times of day, free text.

Every function raises ValueError with a message that never repeats the offending input, because
error bodies must not echo what the client sent (it can be arbitrarily hostile or large).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime

from app.domain.timeutil import MAX_DATE, MAX_INSTANT, MIN_DATE, MIN_INSTANT

_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_HHMM_TEXT = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00")
_MAX_INSTANT_TEXT = 40


def parse_instant(value: object) -> datetime:
    """An ISO 8601 instant with an explicit offset, between 2000 and 2099, as a UTC datetime."""
    example = "an ISO 8601 text with an offset, such as 2026-11-02T10:00:00+05:30"
    if not isinstance(value, str) or len(value) > _MAX_INSTANT_TEXT:
        raise ValueError(f"must be {example}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"must be {example}") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"must include a UTC offset: {example}")
    if not MIN_INSTANT <= parsed < MAX_INSTANT:  # compared before converting: year 1 would overflow
        raise ValueError("must be between the years 2000 and 2099")
    return parsed.astimezone(UTC)


def parse_iso_date(value: object, *, low: date = MIN_DATE, high: date = MAX_DATE) -> date:
    """A calendar date written YYYY-MM-DD, by default between 2000-01-01 and 2100-12-31."""
    if not isinstance(value, str) or not _DATE_TEXT.fullmatch(value):
        raise ValueError("must be a date written YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("must be a real calendar date") from None
    if not low <= parsed <= high:
        raise ValueError(f"must be between {low.isoformat()} and {high.isoformat()}")
    return parsed


def parse_birth_date(value: object) -> date:
    """A date of birth written YYYY-MM-DD; people are older than the booking horizon allows."""
    return parse_iso_date(value, low=date(1900, 1, 1))


def parse_hhmm(value: object) -> int:
    """A time of day written HH:MM, from 00:00 to 24:00, as minutes since midnight."""
    if not isinstance(value, str) or not _HHMM_TEXT.fullmatch(value):
        raise ValueError("must be a time written HH:MM between 00:00 and 24:00")
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def parse_bool_text(value: object) -> bool:
    """The text true or false, nothing else (a query parameter written as yes or 1 is refused).

    A real bool is accepted too: FastAPI validates a parameter's default value the same way.
    """
    if isinstance(value, bool):
        return value
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("must be true or false")


def clean_text(minimum: int, maximum: int, *, multiline: bool = False) -> Callable[[object], str]:
    """A validator for free text: trimmed, bounded, storable, and free of control characters.

    `multiline` allows tab, carriage return and line feed (for a reason or a note).
    """
    allowed = "\t\r\n" if multiline else ""

    def check(value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("must be text")
        text = value.strip()
        if not minimum <= len(text) <= maximum:
            raise ValueError(f"must be {minimum} to {maximum} characters")
        try:
            text.encode("utf-8")  # a lone surrogate from a JSON escape cannot be stored
        except UnicodeEncodeError:
            raise ValueError("contains characters that cannot be stored") from None
        if any(unicodedata.category(c) == "Cc" and c not in allowed for c in text):
            raise ValueError("must not contain control characters")
        return text

    return check
