"""Path and query parameter types: bounded and strict, like the request bodies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Path, Query
from pydantic import BeforeValidator

from app.api.parsing import parse_bool_text
from app.api.schemas.types import IsoDate

MAX_ID = 2_147_483_647

DoctorId = Annotated[int, Path(ge=1, le=MAX_ID)]
StaffId = Annotated[int, Path(ge=1, le=MAX_ID)]
NotificationId = Annotated[int, Path(ge=1, le=MAX_ID)]
DoctorIdQuery = Annotated[int, Query(ge=1, le=MAX_ID)]
PatientId = Annotated[int, Path(ge=1, le=MAX_ID)]
AppointmentId = Annotated[int, Path(ge=1, le=MAX_ID)]
EntityPath = Annotated[int, Path(ge=1, le=MAX_ID)]
OptionalId = Annotated[int | None, Query(ge=1, le=MAX_ID)]

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100_000)]

BoolQuery = Annotated[bool, BeforeValidator(parse_bool_text)]

# A date as YYYY-MM-DD, from 2000-01-01 to 2100-12-31, in the path or in the query string.
DayPath = Annotated[IsoDate, Path()]
DayQuery = Annotated[IsoDate, Query(alias="date")]
RangeStart = Annotated[IsoDate, Query(alias="from")]
RangeEnd = Annotated[IsoDate, Query(alias="to")]
OptionalDayQuery = Annotated[IsoDate | None, Query(alias="date")]
