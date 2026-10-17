"""Field types shared by the request and response schemas.

Requests are strict and bounded (plan 22.5): an id must be a real JSON integer from 1 to
2,147,483,647 (not true, not "1", not 1.5), instants must be ISO 8601 text with an offset, texts
have a length limit and no control characters, and unknown keys are refused.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from app.api.parsing import (
    clean_text,
    parse_birth_date,
    parse_hhmm,
    parse_instant,
    parse_iso_date,
)

EntityId = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]
Instant = Annotated[datetime, BeforeValidator(parse_instant)]
IsoDate = Annotated[date, BeforeValidator(parse_iso_date)]
BirthDate = Annotated[date, BeforeValidator(parse_birth_date)]
TimeOfDay = Annotated[int, BeforeValidator(parse_hhmm)]
PersonName = Annotated[str, BeforeValidator(clean_text(1, 100))]
Reason = Annotated[str, BeforeValidator(clean_text(1, 500, multiline=True))]
Note = Annotated[str, BeforeValidator(clean_text(0, 200, multiline=True))]
PhoneText = Annotated[str, Field(strict=True, max_length=40)]
Weekday = Annotated[int, Field(strict=True, ge=0, le=6)]
DailyCap = Annotated[int, Field(strict=True, ge=1, le=96)]


def _slot_length(value: int) -> int:
    if value not in (15, 30):
        raise ValueError("must be 15 or 30")
    return value


SlotLength = Annotated[int, Field(strict=True), AfterValidator(_slot_length)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
