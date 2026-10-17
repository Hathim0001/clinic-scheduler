"""Spotting symptoms that should not wait for an appointment.

The scheduler is not a clinical tool. This is a plain keyword check on the free-text reason, meant
to put a prominent warning in front of the person booking ("call emergency services"), never to
refuse a booking or to decide anything. A false positive costs one sentence of reading; a miss
is no worse than having no check, so the list favours obvious, serious phrases.
"""

from __future__ import annotations

import re

EMERGENCY_MESSAGE = (
    "These symptoms may be an emergency. Do not wait for an appointment: call 112 (India's "
    "emergency number) or go to the nearest emergency department now."
)

_PHRASES = (
    r"chest (pain|tightness|pressure)",
    r"(severe|difficulty|trouble|shortness of) breath(ing)?",
    r"can'?t breathe",
    r"cannot breathe",
    r"short of breath",
    r"stroke",
    r"face droop(ing)?",
    r"slurred speech",
    r"unconscious",
    r"passed out",
    r"fainted",
    r"seizure",
    r"heavy bleeding",
    r"bleeding (heavily|a lot|won'?t stop)",
    r"coughing (up )?blood",
    r"vomiting blood",
    r"heart attack",
    r"suicid\w*",
    r"overdose",
    r"poison(ed|ing)?",
    r"anaphyla\w*",
    r"severe allergic",
    r"choking",
)
_PATTERN = re.compile(r"\b(?:" + "|".join(_PHRASES) + r")\b", re.IGNORECASE)


def looks_urgent(text: str) -> bool:
    """True when the text mentions a symptom that usually needs emergency care."""
    return _PATTERN.search(text) is not None
