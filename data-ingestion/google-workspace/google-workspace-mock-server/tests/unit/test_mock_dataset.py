"""Dataset validation: the shipped dataset is valid and playable; broken ones report every problem at once."""

from __future__ import annotations

import copy
import json
import re

import pytest

from mock_dataset import MockDataset, read_dataset_or_problems
from mock_settings import DATASETS_DIR
from mock_state import find_unplayable_dataset_parts

SHIPPED_DATASET = DATASETS_DIR / "synthetic_soltech.json"


def shipped_dataset_dict() -> dict:
    return json.loads(SHIPPED_DATASET.read_text(encoding="utf-8"))


def write_dataset(tmp_path, data: dict):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_shipped_dataset_is_valid_and_every_scripted_change_applies():
    dataset, problems = read_dataset_or_problems(SHIPPED_DATASET)

    assert problems == []
    assert find_unplayable_dataset_parts(dataset, SHIPPED_DATASET.name) == []


def test_shipped_dataset_uses_synthetic_addresses_only():
    # Data rule (AGENTS.md): fixtures use invented example.test addresses, never real ones.
    text = SHIPPED_DATASET.read_text(encoding="utf-8")
    addresses = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text))

    assert addresses and all(address.endswith(".example.test") for address in addresses), sorted(addresses)


def test_unknown_field_and_bad_values_are_all_reported_together(tmp_path):
    data = shipped_dataset_dict()
    data["mailbox"]["messages"][0]["subjct"] = "typo in the field name"
    data["calendar"]["events"][0]["start"]["time_zone"] = "Mars/Olympus_Mons"
    data["calendar"]["events"][1]["recurrence"] = "RRULE:FREQ=MONTHLY;COUNT=3"

    dataset, problems = read_dataset_or_problems(write_dataset(tmp_path, data))

    assert dataset is None
    text = " | ".join(p.problem for p in problems)
    assert "subjct" in text and "Mars/Olympus_Mons" in text and "only RRULE" in text
    assert all(p.variable == "dataset broken.json" for p in problems)


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        ({"date_time": "2026-12-02T10:00:00+08:00", "time_zone": "Asia/Manila"}, "local wall time"),
        ({"date_time": "2026-12-02T10:00:00"}, "needs a `time_zone`"),
        ({"date": "2026-12-02", "date_time": "2026-12-02T10:00:00", "time_zone": "Asia/Manila"}, "not both"),
    ],
)
def test_event_times_must_be_unambiguous(tmp_path, start, expected):
    data = shipped_dataset_dict()
    data["calendar"]["events"][0]["start"] = start

    _, problems = read_dataset_or_problems(write_dataset(tmp_path, data))

    assert any(expected in p.problem for p in problems)


def test_message_time_without_an_offset_is_rejected(tmp_path):
    data = shipped_dataset_dict()
    data["mailbox"]["messages"][0]["sent_at"] = "2026-11-17T09:15:00"

    _, problems = read_dataset_or_problems(write_dataset(tmp_path, data))

    assert any("needs a UTC offset" in p.problem for p in problems)


def test_duplicate_ids_are_rejected(tmp_path):
    data = shipped_dataset_dict()
    data["mailbox"]["messages"].append(copy.deepcopy(data["mailbox"]["messages"][0]))

    _, problems = read_dataset_or_problems(write_dataset(tmp_path, data))

    assert any("duplicate message id(s): msg-001" in p.problem for p in problems)


def test_report_stays_ascii_for_non_ascii_dataset_text(tmp_path):
    data = shipped_dataset_dict()
    data["mailbox"]["messages"][0]["campo_extra_ñ"] = 1

    _, problems = read_dataset_or_problems(write_dataset(tmp_path, data))

    assert problems and all(p.problem.isascii() for p in problems)


def test_scripted_change_that_references_a_missing_id_is_reported_with_its_position():
    data = shipped_dataset_dict()
    data["scripted_changes"].append({"kind": "cancel_event", "event_id": "evt-does-not-exist"})
    dataset = MockDataset.model_validate(data)

    problems = find_unplayable_dataset_parts(dataset, "synthetic_soltech.json")

    position = len(data["scripted_changes"]) - 1
    assert [p.problem for p in problems] == [
        f"scripted_changes.{position} (cancel_event): event evt-does-not-exist is not in the calendar"
    ]
