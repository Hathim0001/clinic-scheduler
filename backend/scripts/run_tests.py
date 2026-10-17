"""Run the whole test suite with coverage and write the summary the README links to.

    python scripts/run_tests.py

The integration and API tests need PostgreSQL:  docker compose up -d db
The summary goes to ../coverage.txt, written from Python as UTF-8 with LF endings because
PowerShell 5.1 redirection adds a byte-order mark. The script exits non-zero when a test fails or
when line coverage of the rules (app/domain) and the services (app/services) drops below 80 percent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SUMMARY = BACKEND.parent / "coverage.txt"
RULES_GATE = 80


def run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argument lists, no shell
        [sys.executable, "-m", *command],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def last_lines(text: str, count: int) -> str:
    return "\n".join(text.strip().splitlines()[-count:])


def main() -> int:
    tests = run("pytest", "tests", "-q", "-p", "no:cacheprovider", "--cov=app", "--cov-report=")
    print(tests.stdout, end="")
    print(tests.stderr, end="", file=sys.stderr)
    everything = run("coverage", "report")
    rules = run(
        "coverage",
        "report",
        "--include=app/domain/*,app/services/*",
        f"--fail-under={RULES_GATE}",
    )

    sections = [
        ("Test run", last_lines(tests.stdout, 3)),
        ("Line and branch coverage of app/", everything.stdout.strip()),
        (f"Rules layer (domain and services), gate {RULES_GATE} percent", rules.stdout.strip()),
    ]
    text = "\n\n".join(f"== {title} ==\n{body}" for title, body in sections) + "\n"
    SUMMARY.write_bytes(text.encode("utf-8"))
    print(text)

    failed = tests.returncode != 0 or rules.returncode != 0
    if tests.returncode != 0:
        print("Some tests failed.", file=sys.stderr)
    if rules.returncode != 0:
        print(f"Coverage of the rules layer is below {RULES_GATE} percent.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
