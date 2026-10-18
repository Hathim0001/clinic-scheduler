"""Load test: many simultaneous users booking, reading and cancelling against a running API.

    python scripts/load.py --base-url http://localhost:8000 --users 100 --rounds 5

Each virtual user registers a patient, then repeats: list the doctor's free slots, try to book one
(most users pick the same early slots on purpose, so there are many real collisions), read the
queue, and cancel what they booked. At the end it checks what must hold whatever the load:

- no response is a 5xx (a 409 for a lost race is correct; a 503 for an exhausted pool is not);
- no doctor has two active appointments that overlap, read back through the API.

It prints throughput and the 50th, 95th and 99th percentile latency per kind of request. Run the
server with the rate limit off (RATE_LIMIT_PER_MINUTE=0) or 429s are counted as failures. Needs
nothing beyond the standard library. Creates its own patients ("Load ..."), so use a scratch
database, not the reviewers' seeded one.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from itertools import pairwise
from typing import Any

Sample = tuple[str, int, float]  # (kind, http status, seconds)


def call(base: str, method: str, path: str, body: Any = None) -> tuple[int, Any, float]:
    started = time.perf_counter()
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(  # noqa: S310 - the base URL is chosen by the person running this
        f"{base}/api/v1{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            payload = json.load(response)
            status = response.status
    except urllib.error.HTTPError as error:
        status, payload = error.code, json.load(error)
    except (urllib.error.URLError, TimeoutError):
        status, payload = 599, {}  # no answer at all counts as a server failure
    return status, payload, time.perf_counter() - started


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


class User:
    def __init__(self, base: str, number: int, run_id: int, doctors: list[int], days: list[str]):
        self.base, self.number, self.run_id = base, number, run_id
        self.doctors, self.days = doctors, days
        self.samples: list[Sample] = []
        self.booked: list[int] = []
        self.rng = random.Random(number)  # noqa: S311 - a workload mix, not a secret

    def timed(self, kind: str, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        status, payload, seconds = call(self.base, method, path, body)
        self.samples.append((kind, status, seconds))
        return status, payload

    def register(self) -> int | None:
        phone = f"9{self.run_id % 10**5:05d}{self.number:04d}"
        status, patient = self.timed(
            "register",
            "POST",
            "/patients",
            {
                "name": f"Load {self.run_id}-{self.number}",
                "phone": phone,
                "date_of_birth": "1990-01-01",
            },
        )
        return int(patient["id"]) if status == 201 else None

    def round(self, patient_id: int) -> None:
        doctor = self.rng.choice(self.doctors)
        day = self.rng.choice(self.days)
        status, slots = self.timed("slots", "GET", f"/doctors/{doctor}/slots?date={day}")
        if status == 200 and slots["slots"]:
            # favour the earliest slots so many users collide on purpose
            pick = slots["slots"][min(int(self.rng.expovariate(0.7)), len(slots["slots"]) - 1)]
            status, appointment = self.timed(
                "book",
                "POST",
                "/appointments",
                {
                    "doctor_id": doctor,
                    "patient_id": patient_id,
                    "start_at": pick["start_at_ist"],
                    "reason": "Load test",
                },
            )
            if status == 201:
                self.booked.append(int(appointment["id"]))
        self.timed("queue", "GET", f"/queue?date={day}&doctor_id={doctor}")
        if self.booked and self.rng.random() < 0.6:
            self.timed(
                "cancel",
                "POST",
                f"/appointments/{self.booked.pop()}/cancel",
                {"cancelled_by": "CLINIC"},
            )


def overlapping(base: str, doctors: list[int], days: list[str]) -> list[str]:
    """Any two active appointments of one doctor that overlap, read back through the API."""
    problems = []
    for doctor in doctors:
        for day in days:
            status, queue, _ = call(base, "GET", f"/queue?date={day}&doctor_id={doctor}")
            if status != 200:
                problems.append(f"could not read doctor {doctor} on {day}: HTTP {status}")
                continue
            active = sorted(
                (a for a in queue if a["status"] in ("BOOKED", "COMPLETED", "NO_SHOW")),
                key=lambda a: a["start_at_utc"],
            )
            for first, second in pairwise(active):
                if second["start_at_utc"] < first["end_at_utc"]:
                    problems.append(f"doctor {doctor} on {day}: #{first['id']} and #{second['id']}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=100, help="simultaneous virtual users")
    parser.add_argument("--rounds", type=int, default=5, help="read/book/cancel rounds per user")
    args = parser.parse_args(argv)

    _, doctors, _ = call(args.base_url, "GET", "/doctors")
    doctor_ids = [int(d["id"]) for d in doctors if d["accepting_bookings"]]
    days: list[str] = []
    probe = date.today() + timedelta(days=1)
    while len(days) < 3:
        if probe.weekday() < 5:
            days.append(probe.isoformat())
        probe += timedelta(days=1)
    run_id = uuid.uuid4().int % 10**6

    users = [User(args.base_url, n, run_id, doctor_ids, days) for n in range(args.users)]
    gate = threading.Barrier(args.users)

    def work(user: User) -> None:
        patient_id = user.register()
        gate.wait()  # everyone starts the rounds together
        if patient_id is None:
            return
        for _ in range(args.rounds):
            user.round(patient_id)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.users) as pool:
        list(pool.map(work, users))
    elapsed = time.perf_counter() - started

    samples = [s for user in users for s in user.samples]
    by_kind: dict[str, list[float]] = defaultdict(list)
    statuses: Counter[tuple[str, int]] = Counter()
    for kind, status, seconds in samples:
        by_kind[kind].append(seconds)
        statuses[(kind, status)] += 1
    print(f"{args.users} users x {args.rounds} rounds: {len(samples)} requests in {elapsed:.1f}s")
    print(f"throughput {len(samples) / elapsed:.0f} requests/s")
    for kind, values in sorted(by_kind.items()):
        print(
            f"  {kind:<9} n={len(values):<5} p50={statistics.median(values) * 1000:6.0f} ms "
            f"p95={percentile(values, 0.95) * 1000:6.0f} ms "
            f"p99={percentile(values, 0.99) * 1000:6.0f} ms"
        )
    for (kind, status), count in sorted(statuses.items()):
        print(f"  {kind:<9} HTTP {status}: {count}")

    server_errors = sum(n for (_, status), n in statuses.items() if status >= 500)
    rate_limited = sum(n for (_, status), n in statuses.items() if status == 429)
    overlaps = overlapping(args.base_url, doctor_ids, days)
    successes = statuses[("book", 201)]
    print(
        f"server errors: {server_errors}, rate limited: {rate_limited}, overlaps: {len(overlaps)}"
    )
    for line in overlaps[:5]:
        print("  OVERLAP", line)
    ok = server_errors == 0 and rate_limited == 0 and not overlaps and successes > 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
