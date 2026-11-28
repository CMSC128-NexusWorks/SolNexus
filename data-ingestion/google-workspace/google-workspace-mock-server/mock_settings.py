"""Startup configuration for the mock Google server, validated before it accepts any request.

The mock reads its settings from environment variables only. Validation collects every problem at once
(not just the first), groups them by variable with a fix for each, prints an ASCII-only report and exits
with status 1. That way a misconfigured container fails at boot with one readable message, instead of
starting and misbehaving later.

Why a guard on the environment at all: the mock serves fake Google data. If it ever ran in stage or prod,
the master could be pointed at it and silently ingest invented mail as if it were SolTech's. So it refuses
to start anywhere except local, ci and dev ("fail closed").
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from mock_oauth import DEFAULT_GRANTED_SCOPES, KNOWN_SCOPES

# Where a fake Google is acceptable. Anything else, including "stage" and "prod", is refused.
ALLOWED_MOCK_ENVIRONMENTS = ("local", "ci", "dev")
ALLOWED_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
# Dataset files live next to the code and are selected by name, never by path.
DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
DEFAULT_DATASET = "synthetic_soltech"
# A bare name (no slashes or dots), so MOCK_DATASET can only pick a file inside DATASETS_DIR.
DATASET_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class MockServerSettings:
    """Validated settings. Only built by collect_settings_or_errors, so every instance is known-good."""

    # Which environment this mock runs in; shown by the health route so operators can tell instances apart.
    environment: str
    # Python logging level for the mock's own log lines.
    log_level: str
    # Name of the dataset file (datasets/<name>.json) the mock is seeded from.
    dataset_name: str
    # Lifetime of access tokens issued by the fake token endpoint. Short values exercise token refresh.
    access_token_ttl_seconds: int = 3600
    # What the fake refresh token was consented for. Leaving out the Calendar scope simulates a mailbox that
    # was authorized for Gmail only and never re-consented for Calendar.
    granted_scopes: tuple[str, ...] = DEFAULT_GRANTED_SCOPES

    @property
    def dataset_path(self) -> Path:
        return DATASETS_DIR / f"{self.dataset_name}.json"


@dataclass(frozen=True)
class StartupProblem:
    """One thing that stops the mock from starting: where it is (a variable or dataset file), what is
    wrong, and how to fix it. Shared by settings and dataset validation so both use one report."""

    # The group the report lists it under: an environment variable name, or "dataset <file>".
    variable: str
    problem: str
    fix: str


def collect_settings_or_errors(
    environ: Mapping[str, str],
    datasets_dir: Path = DATASETS_DIR,
) -> tuple[MockServerSettings | None, list[StartupProblem]]:
    """Read and check every setting. Returns (settings, []) when valid, or (None, problems) listing them all.

    Takes the environment as a plain mapping, not os.environ directly, so unit tests can pass a dict.
    Values are stripped and case-normalized first, so " Local " and "local" mean the same thing.
    """
    problems: list[StartupProblem] = []

    environment = environ.get("MOCK_ENVIRONMENT", "local").strip().lower()
    if environment not in ALLOWED_MOCK_ENVIRONMENTS:
        problems.append(
            StartupProblem(
                variable="MOCK_ENVIRONMENT",
                # ascii() keeps the report ASCII-only even if the value contains other characters.
                problem=f"got {ascii(environment)}; must be one of: {', '.join(ALLOWED_MOCK_ENVIRONMENTS)}",
                fix="set MOCK_ENVIRONMENT=local (or ci, dev). The mock serves fake Google data and must "
                "never run in stage or prod, where it could be mistaken for the real Google.",
            )
        )

    log_level = environ.get("MOCK_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in ALLOWED_LOG_LEVELS:
        problems.append(
            StartupProblem(
                variable="MOCK_LOG_LEVEL",
                problem=f"got {ascii(log_level)}; must be one of: {', '.join(ALLOWED_LOG_LEVELS)}",
                fix="set MOCK_LOG_LEVEL=INFO, or leave it unset to use INFO.",
            )
        )

    dataset_name = environ.get("MOCK_DATASET", DEFAULT_DATASET).strip().lower()
    available = sorted(path.stem for path in datasets_dir.glob("*.json"))
    if not DATASET_NAME_PATTERN.match(dataset_name) or dataset_name not in available:
        problems.append(
            StartupProblem(
                variable="MOCK_DATASET",
                problem=f"got {ascii(dataset_name)}; available datasets: {', '.join(available) or '(none found)'}",
                fix=f"set MOCK_DATASET to one of the names above, or leave it unset to use {DEFAULT_DATASET}.",
            )
        )

    access_token_ttl_seconds = read_int_in_range(
        environ,
        "MOCK_ACCESS_TOKEN_TTL_SECONDS",
        default=3600,
        lowest=1,
        highest=86_400,
        problems=problems,
        fix="set MOCK_ACCESS_TOKEN_TTL_SECONDS to 1-86400 (Google uses 3600), or leave it unset.",
    )

    raw_scopes = environ.get("MOCK_OAUTH_GRANTED_SCOPES", " ".join(DEFAULT_GRANTED_SCOPES))
    granted_scopes = tuple(dict.fromkeys(raw_scopes.replace(",", " ").split()))  # de-duplicated, order kept
    unknown_scopes = [scope for scope in granted_scopes if scope not in KNOWN_SCOPES]
    if unknown_scopes or not granted_scopes:
        problems.append(
            StartupProblem(
                variable="MOCK_OAUTH_GRANTED_SCOPES",
                problem="unknown or missing scope(s): "
                + (ascii(" ".join(unknown_scopes)) if unknown_scopes else "(none)"),
                fix=f"use space- or comma-separated values from: {' '.join(sorted(KNOWN_SCOPES))}",
            )
        )

    if problems:
        return None, problems
    return (
        MockServerSettings(
            environment=environment,
            log_level=log_level,
            dataset_name=dataset_name,
            access_token_ttl_seconds=access_token_ttl_seconds,
            granted_scopes=granted_scopes,
        ),
        [],
    )


def read_int_in_range(
    environ: Mapping[str, str],
    variable: str,
    *,
    default: int,
    lowest: int,
    highest: int,
    problems: list[StartupProblem],
    fix: str,
) -> int:
    """An integer setting within bounds. A bad value is recorded as a problem (not raised), so validation can go
    on and report every other problem too; the default is returned as a placeholder in that case."""
    raw = environ.get(variable, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or not lowest <= value <= highest:
        problems.append(
            StartupProblem(variable, f"got {ascii(raw)}; must be a whole number from {lowest} to {highest}", fix)
        )
        return default
    return value


def format_startup_report(problems: list[StartupProblem]) -> str:
    """The ASCII-only startup error report, grouped by variable or file, with a fix under each problem."""
    lines = [
        f"Mock Google server: configuration is invalid ({len(problems)} problem(s)). Nothing was started.",
        "",
    ]
    by_variable: dict[str, list[StartupProblem]] = {}
    for problem in problems:
        by_variable.setdefault(problem.variable, []).append(problem)
    for variable, variable_problems in by_variable.items():
        lines.append(variable)
        for problem in variable_problems:
            lines.append(f"  - {problem.problem}")
            lines.append(f"    fix: {problem.fix}")
    return "\n".join(lines) + "\n"


def load_mock_server_settings_or_exit(environ: Mapping[str, str], stderr: TextIO = sys.stderr) -> MockServerSettings:
    """Settings for startup: valid settings, or the full report on stderr and exit status 1.

    sys.exit raises SystemExit, which uvicorn's app factory does not catch, so the process stops before it
    binds the port and before any request can reach a half-configured mock.
    """
    settings, problems = collect_settings_or_errors(environ)
    if settings is None:
        stderr.write(format_startup_report(problems))
        sys.exit(1)
    return settings
