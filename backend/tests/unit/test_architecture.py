"""T-S04: each layer depends only on the layers below it (plan section 17, ADR-02).

    api -> services -> (domain, persistence) -> core

The domain is the part reviewers read first and the part that must stay testable without a
database, a web framework or a clock, so it gets an allow-list: it may import a handful of pure
standard-library modules and itself, nothing else. Other layers get deny-lists. A package that does
not exist yet is skipped, so each rule starts to apply the day its package appears.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

APP = Path(__file__).resolve().parents[2] / "app"

# Modules a pure rules layer may use. Anything else needs a conscious decision: add it here only if
# it does no I/O and reads no clock.
PURE_STDLIB = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "functools",
        "itertools",
        "math",
        "re",
        "typing",
        "zoneinfo",
    }
)
HTTP_FRAMEWORKS = frozenset({"fastapi", "starlette", "uvicorn", "httpx", "httpx2", "pydantic"})

# Which parts of this project each package may import.
INTERNAL = {
    "core": {"app.core"},
    "domain": {"app.domain"},
    "persistence": {"app.persistence", "app.domain", "app.core"},
    "services": {"app.services", "app.persistence", "app.domain", "app.core"},
}
# Third-party and standard-library modules a non-domain package must not touch.
FORBIDDEN_EXTERNAL = {
    "core": set(),
    "persistence": HTTP_FRAMEWORKS,
    "services": HTTP_FRAMEWORKS,
}


def imported_modules(source: str) -> list[str]:
    """Every module a source text imports; a relative import keeps its leading dots."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    return found


def clock_reads(source: str) -> list[str]:
    """Calls such as datetime.now(), datetime.utcnow() or date.today(), which read the clock."""
    reads: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"now", "utcnow", "today"}
        ):
            reads.append(f"{node.func.attr}() on line {node.lineno}")
    return reads


def is_inside(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def source_files(package: str) -> list[Path]:
    return sorted((APP / package).rglob("*.py"))


def domain_violations(source: str) -> list[str]:
    problems = []
    for module in imported_modules(source):
        top = module.split(".")[0]
        if module.startswith("."):
            problems.append(f"relative import {module!r}")
        elif top in PURE_STDLIB or is_inside(module, "app.domain"):
            continue
        else:
            problems.append(f"imports {module!r}")
    return problems + [f"reads the clock: {read}" for read in clock_reads(source)]


def layer_violations(package: str, source: str) -> list[str]:
    problems = []
    for module in imported_modules(source):
        top = module.split(".")[0]
        if module.startswith("."):
            problems.append(f"relative import {module!r}")
        elif top == "app" and not any(is_inside(module, ok) for ok in INTERNAL[package]):
            problems.append(f"imports {module!r}, which is above or beside this layer")
        elif top in FORBIDDEN_EXTERNAL[package]:
            problems.append(f"imports {module!r}")
    return problems


def test_the_scan_finds_the_source_files() -> None:
    """Guards against a wrong path turning every check below into a vacuous pass."""
    assert len(source_files("domain")) >= 10
    assert len(source_files("persistence")) >= 3


@pytest.mark.parametrize("path", source_files("domain"), ids=lambda p: p.name)
def test_the_domain_is_pure(path: Path) -> None:
    assert domain_violations(path.read_text(encoding="utf-8")) == [], path.name


@pytest.mark.parametrize("package", sorted(FORBIDDEN_EXTERNAL))
def test_a_layer_only_imports_the_layers_below_it(package: str) -> None:
    problems = {
        path.relative_to(APP).as_posix(): found
        for path in source_files(package)
        if (found := layer_violations(package, path.read_text(encoding="utf-8")))
    }
    assert problems == {}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import sqlalchemy", ["imports 'sqlalchemy'"]),
        ("from fastapi import FastAPI", ["imports 'fastapi'"]),
        ("import os", ["imports 'os'"]),
        ("from app.persistence import db", ["imports 'app.persistence'"]),
        ("from . import model", ["relative import '.'"]),
        ("from datetime import datetime\nx = datetime.now()", ["reads the clock: now() on line 2"]),
        ("import date\nd = date.today()", ["imports 'date'", "reads the clock: today() on line 2"]),
        ("from datetime import datetime\nfrom app.domain.model import Status", []),
    ],
)
def test_the_domain_checker_catches_what_it_should(source: str, expected: list[str]) -> None:
    assert domain_violations(source) == expected


def test_the_layer_checker_catches_what_it_should() -> None:
    assert layer_violations("services", "from fastapi import Depends") == ["imports 'fastapi'"]
    assert layer_violations("persistence", "from app.services import booking") == [
        "imports 'app.services', which is above or beside this layer"
    ]
    assert layer_violations("services", "from app.persistence.db import run_in_transaction") == []
