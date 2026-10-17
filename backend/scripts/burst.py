"""Reviewer aid: fire simultaneous bookings at a running API and show how the rules hold.

    python scripts/burst.py --base-url http://localhost:8000 --requests 20

It creates one fresh patient per request, then sends all the booking requests at the same instant
for the same doctor and the same slot. Exactly one should succeed (201) and every other request
should be refused with SLOT_TAKEN (409): never two bookings, never a 5xx.

The slot is found through the API itself (the doctor's first free slot of the next working day),
using the test clock only if the server allows it. Needs nothing beyond the standard library.
"""

from __future__ import annotations

import argparse
import json
import threading
import urllib.error
import urllib.request
import uuid
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any


def call(base: str, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(  # noqa: S310 - the base URL is chosen by the person running this
        f"{base}/api/v1{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def first_free_slot(base: str, doctor_id: int) -> str:
    day = date.today() + timedelta(days=1)
    for _ in range(14):
        status, body = call(base, "GET", f"/doctors/{doctor_id}/slots?date={day.isoformat()}")
        if status == 200 and body["slots"]:
            return str(body["slots"][0]["start_at_ist"])
        day += timedelta(days=1)
    raise SystemExit("No free slot found in the next two weeks.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--doctor-id", type=int, default=1)
    args = parser.parse_args(argv)

    slot = first_free_slot(args.base_url, args.doctor_id)
    print(f"Booking {args.requests} patients into doctor {args.doctor_id} at {slot}, all at once.")
    run_id = uuid.uuid4().int % 10**6
    patients = []
    for n in range(args.requests):
        phone = f"9{run_id:06d}{n:03d}"
        status, patient = call(
            args.base_url,
            "POST",
            "/patients",
            {"name": f"Burst {run_id}-{n}", "phone": phone, "date_of_birth": "1990-01-01"},
        )
        if status != 201:
            raise SystemExit(f"Could not create a patient: {status} {patient}")
        patients.append(patient["id"])

    gate = threading.Barrier(len(patients))

    def book(patient_id: int) -> tuple[int, str]:
        gate.wait()
        status, body = call(
            args.base_url,
            "POST",
            "/appointments",
            {
                "doctor_id": args.doctor_id,
                "patient_id": patient_id,
                "start_at": slot,
                "reason": "Burst test",
            },
        )
        return status, "OK" if status == 201 else body["error"]["code"]

    with ThreadPoolExecutor(max_workers=len(patients)) as pool:
        results = list(pool.map(book, patients))

    for outcome, count in sorted(Counter(results).items()):
        print(f"  HTTP {outcome[0]} {outcome[1]}: {count}")
    successes = sum(1 for status, _ in results if status == 201)
    server_errors = sum(1 for status, _ in results if status >= 500)
    verdict = successes == 1 and server_errors == 0
    print(
        "PASS: exactly one booking, no server errors." if verdict else "FAIL: see the counts above."
    )
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
