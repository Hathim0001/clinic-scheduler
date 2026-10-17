"""Phone numbers: Indian mobiles in one canonical form (A-15, T-X13)."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.phone import normalise_phone

pytestmark = pytest.mark.unit

CANONICAL = re.compile(r"\+91[6-9][0-9]{9}")


def digits_in(zero: int, digits: str = "9876543210") -> str:
    """`digits` written in the decimal digits of another script (give its zero code point)."""
    return "".join(chr(zero + int(digit)) for digit in digits)


@pytest.mark.parametrize(
    "raw",
    [
        "9876543210",
        "98765 43210",
        "98765-43210",
        "98765.43210",
        "(98765) 43210",
        "+91-98765-43210",
        "+91 98765 43210",
        "+919876543210",
        "919876543210",
        "91 98765 43210",
        "09876543210",
        "0 98765 43210",
        "  9876543210  ",
        "9876543210\n",
    ],
)
def test_the_ways_people_type_a_number_all_give_one_canonical_form(raw: str) -> None:
    assert normalise_phone(raw) == "+919876543210"


@pytest.mark.parametrize("first_digit", "6789")
def test_mobile_numbers_start_with_6_to_9(first_digit: str) -> None:
    assert normalise_phone(f"{first_digit}123456789") == f"+91{first_digit}123456789"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "1234567890",  # T-X13: starts with 1
        "5876543210",  # starts with 5
        "0123456789",  # a trunk prefix 0 followed by only nine digits
        "+9198765",  # too short
        "987654321",  # nine digits
        "98765432101",  # eleven digits
        "+91 98765 432100",  # too long after the country code
        "+919876543210123",
        "+1 9876543210",  # another country code
        "+44 7911 123456",
        "0091 9876543210",  # international prefix is not accepted
        "+91 0 9876543210",
        "+910987654321",  # a zero where the mobile digit should be
        "98765 4321a",
        "phone",
        "' OR 1=1--",  # T-X13
        "9876543210; DROP TABLE patients",
        "9876543210\x00",
        "98765\n43210",
        "98765\t43210",
        "+9876543210",  # '+' without the 91 country code
        "++919876543210",
        "98765_43210",
        "98765/43210",
    ],
)
def test_anything_that_is_not_an_indian_mobile_number_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="phone"):
        normalise_phone(raw)


@pytest.mark.parametrize(
    "raw",
    [
        digits_in(0x0660),  # Arabic-Indic digits (T-X13)
        digits_in(0x06F0),  # Extended Arabic-Indic digits
        digits_in(0x0966),  # Devanagari digits
        digits_in(0xFF10),  # full-width digits
        "+" + digits_in(0x0966, "919876543210"),  # country code and number in Devanagari
        "98765 4321" + chr(0x0660),  # a single Arabic-Indic zero at the end
        chr(0x200F) + "9876543210",  # a right-to-left mark in front
        "9876543210" + chr(0xA0),  # a non-breaking space behind
    ],
    ids=[
        "arabic-indic",
        "extended",
        "devanagari",
        "full-width",
        "devanagari with +91",
        "last digit",
        "bidi mark",
        "nbsp",
    ],
)
def test_digits_from_other_scripts_are_rejected_not_converted(raw: str) -> None:
    """int() and str.isdigit() accept these, so a naive check would let them through."""
    with pytest.raises(ValueError, match="phone"):
        normalise_phone(raw)


def test_an_enormous_input_is_rejected_quickly() -> None:
    with pytest.raises(ValueError, match="phone"):
        normalise_phone("9" * 100_000)
    with pytest.raises(ValueError, match="phone"):
        normalise_phone(" " * 100_000 + "9876543210x")


def test_normalising_twice_changes_nothing() -> None:
    once = normalise_phone("(98765) 43210")
    assert normalise_phone(once) == once


@given(st.text())
def test_any_text_is_either_rejected_with_value_error_or_canonical(raw: str) -> None:
    try:
        result = normalise_phone(raw)
    except ValueError:
        return
    assert CANONICAL.fullmatch(result)


@given(st.from_regex(r"[6-9][0-9]{9}", fullmatch=True))
def test_ten_digits_are_prefixed_and_idempotent(digits: str) -> None:
    result = normalise_phone(digits)
    assert result == "+91" + digits
    assert normalise_phone(result) == result
