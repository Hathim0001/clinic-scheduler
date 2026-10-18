"""A few in-process counters, exposed at `/metrics` in Prometheus text format.

They answer "is it healthy and what is it refusing?" without access to the host's log viewer:
requests by method and status, rejected requests by error code, and total request time. Labels are
only the method, the status code and the error code, never paths with ids, names or phone numbers,
so the output holds no personal data and its size cannot grow with traffic. The counters live in
this process and reset when it restarts; with several instances each reports its own.
"""

from __future__ import annotations

import threading
from collections import Counter

_lock = threading.Lock()
_requests: Counter[tuple[str, int]] = Counter()
_rejections: Counter[str] = Counter()
_duration_ms = 0.0


def count_request(method: str, status: int, duration_ms: float) -> None:
    global _duration_ms
    with _lock:
        _requests[(method, status)] += 1
        _duration_ms += duration_ms


def count_rejection(code: str) -> None:
    with _lock:
        _rejections[code] += 1


def reset() -> None:
    """For tests."""
    global _duration_ms
    with _lock:
        _requests.clear()
        _rejections.clear()
        _duration_ms = 0.0


def render() -> str:
    with _lock:
        lines = [
            "# HELP clinic_requests_total Requests answered, by method and status.",
            "# TYPE clinic_requests_total counter",
        ]
        lines += [
            f'clinic_requests_total{{method="{method}",status="{status}"}} {n}'
            for (method, status), n in sorted(_requests.items())
        ]
        lines += [
            "# HELP clinic_rejections_total Requests refused by a rule, by error code.",
            "# TYPE clinic_rejections_total counter",
        ]
        lines += [
            f'clinic_rejections_total{{code="{code}"}} {n}'
            for code, n in sorted(_rejections.items())
        ]
        lines += [
            "# HELP clinic_request_duration_ms_sum Total time spent answering requests.",
            "# TYPE clinic_request_duration_ms_sum counter",
            f"clinic_request_duration_ms_sum {round(_duration_ms, 1)}",
        ]
    return "\n".join(lines) + "\n"
