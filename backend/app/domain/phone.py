"""Phone numbers: Indian mobiles in one canonical form, +91 followed by ten digits (A-15)."""

from __future__ import annotations

import re

MESSAGE = "Not a valid Indian mobile phone number: use ten digits starting with 6 to 9."
# Far longer than any real way of writing a number, short enough to refuse junk without scanning it.
MAX_RAW_LENGTH = 40

_SEPARATORS = re.compile(r"[ \-().]")
# +91 or 91 in front, a trunk 0 in front, or just the ten digits. [0-9], never \d: \d accepts the
# digits of every script.
_FORMS = (
    re.compile(r"\+?91([6-9][0-9]{9})"),
    re.compile(r"0([6-9][0-9]{9})"),
    re.compile(r"([6-9][0-9]{9})"),
)


def normalise_phone(raw: str) -> str:
    """Return the canonical `+91XXXXXXXXXX` form, or raise ValueError.

    Accepts the number as people type it: with spaces, hyphens, dots or brackets, with or without
    the +91 / 91 / 0 prefix. The ten digits must start with 6 to 9. Only ASCII digits are accepted:
    digits from other scripts are rejected rather than silently converted.
    """
    if len(raw) > MAX_RAW_LENGTH or not raw.isascii():
        raise ValueError(MESSAGE)
    squeezed = _SEPARATORS.sub("", raw.strip())
    for form in _FORMS:
        match = form.fullmatch(squeezed)
        if match:
            return "+91" + match.group(1)
    raise ValueError(MESSAGE)
