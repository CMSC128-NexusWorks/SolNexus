"""Startup configuration validation: every problem reported at once, ASCII-only, then exit status 1."""

from __future__ import annotations

import io

import pytest

from mock_settings import collect_settings_or_errors, format_startup_report, load_mock_server_settings_or_exit


def test_defaults_are_a_valid_local_mock():
    settings, problems = collect_settings_or_errors({})

    assert problems == []
    assert settings is not None
    assert (settings.environment, settings.log_level, settings.dataset_name) == ("local", "INFO", "synthetic_soltech")


@pytest.mark.parametrize("environment", ["local", "ci", "dev", " Dev "])
def test_mock_runs_in_local_ci_and_dev(environment):
    settings, problems = collect_settings_or_errors({"MOCK_ENVIRONMENT": environment})

    assert problems == []
    assert settings.environment == environment.strip().lower()


@pytest.mark.parametrize("environment", ["stage", "prod", "production", ""])
def test_mock_refuses_any_environment_where_real_data_flows(environment):
    settings, problems = collect_settings_or_errors({"MOCK_ENVIRONMENT": environment})

    assert settings is None
    assert [p.variable for p in problems] == ["MOCK_ENVIRONMENT"]
    assert "never run in stage or prod" in problems[0].fix


def test_every_problem_is_reported_at_once_not_just_the_first():
    _, problems = collect_settings_or_errors({"MOCK_ENVIRONMENT": "prod", "MOCK_LOG_LEVEL": "LOUD"})

    assert {p.variable for p in problems} == {"MOCK_ENVIRONMENT", "MOCK_LOG_LEVEL"}


def test_report_is_ascii_only_grouped_by_variable_with_a_fix_each():
    # A non-ASCII value must not make the report non-ASCII (it is escaped, not printed raw).
    _, problems = collect_settings_or_errors({"MOCK_ENVIRONMENT": "pröd", "MOCK_LOG_LEVEL": "LOUD"})

    report = format_startup_report(problems)

    assert report.isascii()
    assert "2 problem(s)" in report
    assert "\nMOCK_ENVIRONMENT\n" in report and "\nMOCK_LOG_LEVEL\n" in report
    assert report.count("    fix: ") == 2


def test_invalid_settings_print_the_report_and_exit_with_status_1():
    stderr = io.StringIO()

    with pytest.raises(SystemExit) as exit_info:
        load_mock_server_settings_or_exit({"MOCK_ENVIRONMENT": "prod"}, stderr=stderr)

    assert exit_info.value.code == 1
    assert "Nothing was started" in stderr.getvalue()


@pytest.mark.parametrize("dataset", ["no_such_dataset", "../synthetic_soltech", "datasets/synthetic_soltech"])
def test_dataset_must_be_a_bare_name_of_an_existing_file(dataset):
    # Path-like values are refused, so MOCK_DATASET can never read a file outside datasets/.
    _, problems = collect_settings_or_errors({"MOCK_DATASET": dataset})

    assert [p.variable for p in problems] == ["MOCK_DATASET"]
    assert "synthetic_soltech" in problems[0].problem  # the report lists what is available
