"""Phone numbers: Indian mobiles in one canonical form, +91 followed by ten digits (A-15)."""

from __future__ import annotations


def normalise_phone(raw: str) -> str:
    """Return the canonical `+91XXXXXXXXXX` form, or raise ValueError.

    Accepts the number as people type it: with spaces, hyphens, dots or brackets, with or without
    the +91 / 91 / 0 prefix. The ten digits must start with 6 to 9. Only ASCII digits are accepted:
    digits from other scripts are rejected rather than silently converted.
    """
    raise NotImplementedError
