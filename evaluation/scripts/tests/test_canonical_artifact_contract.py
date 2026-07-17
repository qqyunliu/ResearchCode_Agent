"""Repository-level contracts for the canonical Pilot artifacts.

These tests prevent a validated dataset, its compatibility alias, and the
declared schema generation from silently drifting apart.
"""

from __future__ import annotations

import json
from pathlib import Path


EVALUATION_ROOT = Path(__file__).resolve().parents[2]
CURRENT_DATASET_VERSION = "1.4"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_canonical_alias_is_byte_identical_to_pilot_current() -> None:
    current = EVALUATION_ROOT / "datasets" / "pilot-current.jsonl"
    alias = EVALUATION_ROOT / "datasets" / "pilot.jsonl"

    assert alias.read_bytes() == current.read_bytes()


def test_pilot_current_uses_schema_1_4_dataset_version() -> None:
    current = EVALUATION_ROOT / "datasets" / "pilot-current.jsonl"
    records = _load_jsonl(current)

    assert records
    assert {record["dataset_version"] for record in records} == {
        CURRENT_DATASET_VERSION
    }
