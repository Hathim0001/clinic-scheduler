"""Field types shared by the request and response schemas.

Requests are strict and bounded (plan 22.5): an id must be a real JSON integer from 1 to
2,147,483,647 (not true, not "1", not 1.5), instants must be ISO 8601 text with an offset, texts
have a length limit and no control characters, and unknown keys are refused.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema

from app.api.parsing import (
    clean_text,
    parse_birth_date,
    parse_hhmm,
    parse_instant,
    parse_iso_date,
)

# The custom parsers below accept text, so the OpenAPI document must say text too: WithJsonSchema
# gives the documented shape without changing how the value is validated.
EntityId = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
Instant = Annotated[
    datetime,
    BeforeValidator(parse_instant),
    WithJsonSchema(
        {
            "type": "string",
            "format": "date-time",
            "examples": ["2026-11-02T10:00:00+05:30"],
            "description": "ISO 8601 with an explicit UTC offset, between the years 2000 and 2099.",
        }
    ),
]
IsoDate = Annotated[
    date,
    BeforeValidator(parse_iso_date),
    WithJsonSchema(
        {
            "type": "string",
            "format": "date",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
            "examples": ["2026-11-02"],
            "description": "A calendar date, YYYY-MM-DD, from 2000-01-01 to 2100-12-31.",
        }
    ),
]
BirthDate = Annotated[
    date,
    BeforeValidator(parse_birth_date),
    WithJsonSchema(
        {
            "type": "string",
            "format": "date",
            "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
            "examples": ["1985-04-02"],
            "description": "A date of birth, YYYY-MM-DD, from 1900-01-01 and not after today.",
        }
    ),
]
TimeOfDay = Annotated[
    int,
    BeforeValidator(parse_hhmm),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": "^(?:[01][0-9]|2[0-3]):[0-5][0-9]$|^24:00$",
            "examples": ["09:00"],
            "description": "A time of day, HH:MM, from 00:00 to 24:00 (India time).",
        }
    ),
]


def _text(minimum: int, maximum: int) -> WithJsonSchema:
    return WithJsonSchema({"type": "string", "minLength": minimum, "maxLength": maximum})


PersonName = Annotated[str, BeforeValidator(clean_text(1, 100)), _text(1, 100)]
Reason = Annotated[str, BeforeValidator(clean_text(1, 500, multiline=True)), _text(1, 500)]
Note = Annotated[str, BeforeValidator(clean_text(0, 200, multiline=True)), _text(0, 200)]
PhoneText = Annotated[
    str,
    Field(strict=True, max_length=40),
    WithJsonSchema(
        {
            "type": "string",
            "maxLength": 40,
            "examples": ["98765 43210", "+91-98765-43210"],
            "description": "An Indian mobile number; stored as +91 and ten digits starting 6 to 9.",
        }
    ),
]
Weekday = Annotated[int, Field(strict=True, ge=0, le=6)]
DailyCap = Annotated[int, Field(strict=True, ge=1, le=96)]


def _slot_length(value: int) -> int:
    if value not in (15, 30):
        raise ValueError("must be 15 or 30")
    return value


SlotLength = Annotated[
    int,
    Field(strict=True),
    AfterValidator(_slot_length),
    WithJsonSchema({"type": "integer", "enum": [15, 30], "description": "Minutes per slot."}),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
