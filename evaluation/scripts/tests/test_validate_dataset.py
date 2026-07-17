#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for validate_dataset.py.

Each test creates temporary JSONL and schema files, runs the validator, and
asserts on the resulting errors.  All fixtures are self-contained -- no
external dataset files are needed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from validate_dataset import (  # noqa: E402
    ValidationError,
    validate_dataset,
    load_schema,
    HAS_JSONSCHEMA,
)

# Path to the real schema shipped with the project
_SCHEMA_PATH = str(
    _SCRIPTS_DIR.parent / "schema" / "evaluation_case.schema.json"
)


# ===================================================================
# Helper: build a minimal valid record
# ===================================================================

_COMMIT_SHA = "a" * 40  # 40 hex chars

# Valid 64-char hex stable entity keys for test fixtures
_STABLE_KEY_A = "a" * 64
_STABLE_KEY_B = "b" * 64
_STABLE_KEY_C = "c" * 64


def _make_valid_record(**overrides: object) -> dict:
    """Return a minimal record that satisfies both schema and semantic rules.

    Override any field by passing keyword arguments.  Pass ``None`` to remove
    a field entirely.
    """
    base: dict = {
        "dataset_version": "1.0",
        "question_id": "ruoyi-qa-0001",
        "question_fingerprint": "fp_abc123",
        "repo_id": "ruoyi-vue",
        "commit_sha": _COMMIT_SHA,
        "split": "development",
        "task_type": "CODE_QA",
        "language": "en",
        "difficulty": "medium",
        "question": "Where is the user list API implemented?",
        "source_answerable": True,
        "system_answerable": "full",
        "question_origin": "human",
        "gold_status": "machine_proposed",
        "execution_status": "executable",
        "annotation": {
            "annotator": "evidence_annotator_A",
            "reviewer": "adversarial_reviewer_A",
            "review_status": "accepted",
        },
        "provenance": {
            "source_files": ["src/main/java/UserController.java"],
            "generation_method": "manual_code_inspection",
            "created_at": "2026-01-15T10:00:00Z",
        },
    }
    for key, value in overrides.items():
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value
    return base


def _make_gold_entity(
    stable_entity_key: str = _STABLE_KEY_A,
    entity_type: str = "java_method",
    qualified_name: str = "Foo.bar",
    file_path: str = "src/Foo.java",
    start_line: int = 10,
    end_line: int = 50,
    relevance: str = "must_recall",
) -> dict:
    """Return a minimal valid gold_entity with all required fields."""
    return {
        "stable_entity_key": stable_entity_key,
        "entity_type": entity_type,
        "qualified_name": qualified_name,
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "relevance": relevance,
    }


def _write_jsonl(tmp_dir: str, records: list[dict]) -> str:
    """Write records to a JSONL file and return its path."""
    path = os.path.join(tmp_dir, "dataset.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


# ===================================================================
# Tests
# ===================================================================


class TestValidSample:
    """A well-formed record should pass all validation."""

    def test_valid_sample_passes(self, tmp_path: Path) -> None:
        dataset_path = _write_jsonl(
            str(tmp_path), [_make_valid_record()]
        )
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        assert total == 1
        assert len(errors) == 0, f"Unexpected errors: {errors}"


class TestSchemaErrors:
    """Test that JSON Schema violations are caught."""

    def test_invalid_sha_format(self, tmp_path: Path) -> None:
        """commit_sha must be 40 hex characters."""
        rec = _make_valid_record(commit_sha="not-a-valid-sha")
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        assert total == 1
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1, "Expected schema error for bad SHA"
        assert any("commit_sha" in e.field for e in schema_errors)

    def test_missing_required_field(self, tmp_path: Path) -> None:
        """question_id is required."""
        rec = _make_valid_record()
        del rec["question_id"]
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        assert total == 1
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1

    def test_invalid_enum_value(self, tmp_path: Path) -> None:
        """split must be one of the allowed values."""
        rec = _make_valid_record(split="train")
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        assert total == 1
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1


class TestAnnotatorReviewerSeparation:
    """Rule 5: annotator must differ from reviewer."""

    def test_same_annotator_reviewer_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            annotation={
                "annotator": "agent_A",
                "reviewer": "agent_A",
                "review_status": "accepted",
            }
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        sep_errors = [
            e for e in errors if e.rule == "annotator_reviewer_separation"
        ]
        assert len(sep_errors) == 1
        assert "annotator" in sep_errors[0].reason.lower() or "reviewer" in sep_errors[0].reason.lower()


class TestDuplicateFingerprint:
    """Rule 6: question_fingerprint must be unique within the dataset."""

    def test_duplicate_fingerprint_fails(self, tmp_path: Path) -> None:
        rec1 = _make_valid_record(
            question_id="ruoyi-qa-0001",
            question_fingerprint="dup_fp",
        )
        rec2 = _make_valid_record(
            question_id="ruoyi-qa-0002",
            question_fingerprint="dup_fp",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec1, rec2])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        fp_errors = [
            e for e in errors if e.rule == "question_fingerprint_uniqueness"
        ]
        assert len(fp_errors) >= 2, "Expected error on both duplicate records"


class TestSplitFingerprintUniqueness:
    """Rule 7: same fingerprint must not appear in different splits."""

    def test_cross_split_fingerprint_fails(self, tmp_path: Path) -> None:
        rec1 = _make_valid_record(
            question_id="ruoyi-qa-0001",
            question_fingerprint="cross_fp",
            split="development",
        )
        rec2 = _make_valid_record(
            question_id="ruoyi-qa-0002",
            question_fingerprint="cross_fp",
            split="holdout",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec1, rec2])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        # Both duplicate + cross-split errors
        split_errors = [
            e for e in errors if e.rule == "split_fingerprint_uniqueness"
        ]
        assert len(split_errors) >= 2


class TestTraceChainGold:
    """Rule 1: TRACE_CHAIN + source_answerable=true + system_answerable in (full,partial)
    must have gold_nodes and gold_edges."""

    def test_missing_gold_nodes_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=True,
            system_answerable="full",
            gold_nodes=[],
            gold_edges=[
                {
                    "source_key": _STABLE_KEY_A,
                    "target_key": _STABLE_KEY_B,
                    "relation_type": "CALLS_METHOD",
                }
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        trace_errors = [e for e in errors if e.rule == "task_specific_gold"]
        assert len(trace_errors) >= 1
        assert any("gold_nodes" in e.field for e in trace_errors)

    def test_missing_gold_edges_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=True,
            system_answerable="full",
            gold_nodes=[
                {
                    "stable_entity_key": _STABLE_KEY_A,
                    "entity_type": "java_method",
                    "qualified_name": "Foo.bar",
                    "file_path": "src/Foo.java",
                }
            ],
            gold_edges=[],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        trace_errors = [e for e in errors if e.rule == "task_specific_gold"]
        assert len(trace_errors) >= 1
        assert any("gold_edges" in e.field for e in trace_errors)

    def test_trace_chain_with_gold_passes(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=True,
            system_answerable="full",
            gold_nodes=[
                {
                    "stable_entity_key": _STABLE_KEY_A,
                    "entity_type": "java_method",
                    "qualified_name": "Foo.bar",
                    "file_path": "src/Foo.java",
                },
                {
                    "stable_entity_key": _STABLE_KEY_B,
                    "entity_type": "java_method",
                    "qualified_name": "Baz.qux",
                    "file_path": "src/Baz.java",
                },
            ],
            gold_edges=[
                {
                    "source_key": _STABLE_KEY_A,
                    "target_key": _STABLE_KEY_B,
                    "relation_type": "CALLS_METHOD",
                    "indexed_in_system": True,
                }
            ],
            provenance={
                "source_files": ["src/Foo.java", "src/Baz.java"],
                "generation_method": "manual_code_inspection",
                "created_at": "2026-01-15T10:00:00Z",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        trace_errors = [e for e in errors if e.rule == "task_specific_gold"]
        assert len(trace_errors) == 0

    def test_trace_chain_source_unanswerable_skips_gold_requirement(
        self, tmp_path: Path
    ) -> None:
        """source_answerable=false should not require gold_nodes/gold_edges."""
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=False,
            system_answerable="insufficient",
            gold_nodes=[],
            gold_edges=[],
            expected_uncertainties=[
                {
                    "condition": "no source evidence",
                    "description": "Cannot trace chain without source",
                }
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        trace_errors = [e for e in errors if e.rule == "task_specific_gold"]
        assert len(trace_errors) == 0


class TestLineRangeValidity:
    """Rule 3: start_line must be <= end_line."""

    def test_start_greater_than_end_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_entities=[
                _make_gold_entity(start_line=50, end_line=10),
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        range_errors = [e for e in errors if e.rule == "line_range_validity"]
        assert len(range_errors) == 1
        assert "50" in range_errors[0].reason and "10" in range_errors[0].reason

    def test_valid_range_passes(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_entities=[
                _make_gold_entity(start_line=10, end_line=50),
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        range_errors = [e for e in errors if e.rule == "line_range_validity"]
        assert len(range_errors) == 0

    def test_evidence_range_invalid(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            required_claims=[
                {
                    "claim": "The API is at /api/users",
                    "evidence_file": "src/UserController.java",
                    "evidence_ranges": [
                        {
                            "file_path": "src/UserController.java",
                            "start_line": 100,
                            "end_line": 20,
                        }
                    ],
                }
            ]
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        range_errors = [e for e in errors if e.rule == "line_range_validity"]
        assert len(range_errors) == 1


class TestDanglingEdge:
    """Rule 4: gold_edges endpoints must exist in gold_nodes."""

    def test_dangling_source_key_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=True,
            system_answerable="full",
            gold_nodes=[
                {
                    "stable_entity_key": _STABLE_KEY_B,
                    "entity_type": "java_method",
                    "qualified_name": "Baz.qux",
                    "file_path": "src/Baz.java",
                },
            ],
            gold_edges=[
                {
                    "source_key": "f" * 64,  # not in nodes
                    "target_key": _STABLE_KEY_B,
                    "relation_type": "CALLS_METHOD",
                }
            ],
            provenance={
                "source_files": ["src/Baz.java"],
                "generation_method": "manual_code_inspection",
                "created_at": "2026-01-15T10:00:00Z",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        edge_errors = [
            e for e in errors if e.rule == "edge_endpoint_existence"
        ]
        assert len(edge_errors) >= 1
        assert "source_key" in edge_errors[0].field

    def test_dangling_target_key_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=True,
            system_answerable="full",
            gold_nodes=[
                {
                    "stable_entity_key": _STABLE_KEY_A,
                    "entity_type": "java_method",
                    "qualified_name": "Foo.bar",
                    "file_path": "src/Foo.java",
                },
            ],
            gold_edges=[
                {
                    "source_key": _STABLE_KEY_A,
                    "target_key": "f" * 64,  # not in nodes
                    "relation_type": "CALLS_METHOD",
                }
            ],
            provenance={
                "source_files": ["src/Foo.java"],
                "generation_method": "manual_code_inspection",
                "created_at": "2026-01-15T10:00:00Z",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        edge_errors = [
            e for e in errors if e.rule == "edge_endpoint_existence"
        ]
        assert len(edge_errors) >= 1
        assert "target_key" in edge_errors[0].field


class TestStatusMetricExclusion:
    """Rule 8: rejected/needs_review must not be machine_verified/human_verified."""

    def test_rejected_with_machine_verified_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_status="machine_verified",
            annotation={
                "annotator": "annotator_A",
                "reviewer": "reviewer_A",
                "review_status": "rejected",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        status_errors = [
            e for e in errors if e.rule == "status_metric_exclusion"
        ]
        assert len(status_errors) == 1

    def test_needs_review_with_human_verified_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_status="human_verified",
            annotation={
                "annotator": "annotator_A",
                "reviewer": "reviewer_A",
                "review_status": "needs_review",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        status_errors = [
            e for e in errors if e.rule == "status_metric_exclusion"
        ]
        assert len(status_errors) == 1

    def test_accepted_with_machine_verified_passes(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_status="machine_verified",
            annotation={
                "annotator": "annotator_A",
                "reviewer": "reviewer_A",
                "review_status": "accepted",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        status_errors = [
            e for e in errors if e.rule == "status_metric_exclusion"
        ]
        assert len(status_errors) == 0


class TestAnswerableUncertainties:
    """Rule 9: source_answerable=false must have non-empty expected_uncertainties."""

    def test_source_answerable_false_without_uncertainties_fails(
        self, tmp_path: Path
    ) -> None:
        rec = _make_valid_record(
            source_answerable=False,
            system_answerable="insufficient",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        unc_errors = [
            e for e in errors if e.rule == "answerable_uncertainties"
        ]
        assert len(unc_errors) == 1

    def test_source_answerable_false_with_uncertainties_passes(
        self, tmp_path: Path
    ) -> None:
        rec = _make_valid_record(
            source_answerable=False,
            system_answerable="insufficient",
            expected_uncertainties=[
                {
                    "condition": "no matching API endpoint",
                    "description": "The system cannot find the referenced API",
                }
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        unc_errors = [
            e for e in errors if e.rule == "answerable_uncertainties"
        ]
        assert len(unc_errors) == 0


class TestRetrievalCoverage:
    """Rule 2: retrieval-layer samples need must_recall or source_answerable=false."""

    def test_retrieval_without_must_recall_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            evaluation_layers=["retrieval"],
            source_answerable=True,
            system_answerable="full",
            gold_entities=[
                _make_gold_entity(relevance="acceptable_alternative"),
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        ret_errors = [
            e for e in errors if e.rule == "retrieval_entity_coverage"
        ]
        assert len(ret_errors) == 1

    def test_retrieval_with_must_recall_passes(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            evaluation_layers=["retrieval"],
            source_answerable=True,
            system_answerable="full",
            gold_entities=[
                _make_gold_entity(relevance="must_recall"),
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        ret_errors = [
            e for e in errors if e.rule == "retrieval_entity_coverage"
        ]
        assert len(ret_errors) == 0

    def test_retrieval_source_unanswerable_skips_requirement(
        self, tmp_path: Path
    ) -> None:
        """source_answerable=false should not require must_recall entities."""
        rec = _make_valid_record(
            evaluation_layers=["retrieval"],
            source_answerable=False,
            system_answerable="insufficient",
            gold_entities=[],
            expected_uncertainties=[
                {
                    "condition": "no source",
                    "description": "Cannot retrieve without source",
                }
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        ret_errors = [
            e for e in errors if e.rule == "retrieval_entity_coverage"
        ]
        assert len(ret_errors) == 0


class TestProvenanceCoverage:
    """Rule 10: provenance.source_files must cover files in gold evidence."""

    def test_missing_source_file_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_entities=[
                _make_gold_entity(file_path="src/Other.java"),
            ],
            provenance={
                "source_files": ["src/Main.java"],
                "generation_method": "manual_code_inspection",
                "created_at": "2026-01-15T10:00:00Z",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        prov_errors = [e for e in errors if e.rule == "provenance_coverage"]
        assert len(prov_errors) == 1
        assert "src/Other.java" in prov_errors[0].reason


class TestEmptyDataset:
    """An empty dataset should succeed with 0 errors."""

    def test_empty_file_succeeds(self, tmp_path: Path) -> None:
        dataset_path = _write_jsonl(str(tmp_path), [])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        assert total == 0
        assert len(errors) == 0


class TestCLIMain:
    """Test the CLI entry point."""

    def test_cli_help(self) -> None:
        """--help should exit with SystemExit(0)."""
        from validate_dataset import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_cli_valid_file(self, tmp_path: Path) -> None:
        """CLI should return 0 for a valid dataset."""
        from validate_dataset import main

        dataset_path = _write_jsonl(str(tmp_path), [_make_valid_record()])
        exit_code = main([dataset_path, "--schema", _SCHEMA_PATH])
        assert exit_code == 0

    def test_cli_invalid_file(self, tmp_path: Path) -> None:
        """CLI should return 1 for an invalid dataset."""
        from validate_dataset import main

        rec = _make_valid_record(commit_sha="bad")
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        exit_code = main([dataset_path, "--schema", _SCHEMA_PATH])
        assert exit_code == 1

    def test_cli_missing_file(self, tmp_path: Path) -> None:
        """CLI should return 1 for a nonexistent file."""
        from validate_dataset import main

        exit_code = main([
            str(tmp_path / "nonexistent.jsonl"),
            "--schema", _SCHEMA_PATH,
        ])
        assert exit_code == 1


# ===================================================================
# Schema v1.2.0 new rules
# ===================================================================


class TestEntityStableKeyFormat:
    """Rule 11: gold_entities must have stable_entity_key as 64-char hex string."""

    def test_valid_stable_key_passes(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_entities=[_make_gold_entity(stable_entity_key="a" * 64)],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        key_errors = [e for e in errors if e.rule == "entity_stable_key_format"]
        assert len(key_errors) == 0

    def test_short_stable_key_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_entities=[_make_gold_entity(stable_entity_key="abc123")],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        key_errors = [e for e in errors if e.rule == "entity_stable_key_format"]
        assert len(key_errors) == 1

    def test_non_hex_stable_key_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            gold_entities=[_make_gold_entity(stable_entity_key="g" * 64)],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        key_errors = [e for e in errors if e.rule == "entity_stable_key_format"]
        assert len(key_errors) == 1


class TestEdgeIndexedChainComplete:
    """Rule 12: gold_edges with indexed_in_system=false requires chain_complete=false."""

    def test_unindexed_edge_without_chain_complete_false_fails(
        self, tmp_path: Path
    ) -> None:
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=True,
            system_answerable="full",
            gold_nodes=[
                {
                    "stable_entity_key": _STABLE_KEY_A,
                    "entity_type": "java_method",
                    "qualified_name": "Foo.bar",
                    "file_path": "src/Foo.java",
                },
                {
                    "stable_entity_key": _STABLE_KEY_B,
                    "entity_type": "java_method",
                    "qualified_name": "Baz.qux",
                    "file_path": "src/Baz.java",
                },
            ],
            gold_edges=[
                {
                    "source_key": _STABLE_KEY_A,
                    "target_key": _STABLE_KEY_B,
                    "relation_type": "CALLS_METHOD",
                    "indexed_in_system": False,
                }
            ],
            # chain_complete not set to false -> should fail
            provenance={
                "source_files": ["src/Foo.java", "src/Baz.java"],
                "generation_method": "manual_code_inspection",
                "created_at": "2026-01-15T10:00:00Z",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        chain_errors = [
            e for e in errors if e.rule == "edge_indexed_chain_complete"
        ]
        assert len(chain_errors) == 1

    def test_unindexed_edge_with_chain_complete_false_passes(
        self, tmp_path: Path
    ) -> None:
        rec = _make_valid_record(
            task_type="TRACE_CHAIN",
            source_answerable=True,
            system_answerable="full",
            gold_nodes=[
                {
                    "stable_entity_key": _STABLE_KEY_A,
                    "entity_type": "java_method",
                    "qualified_name": "Foo.bar",
                    "file_path": "src/Foo.java",
                },
                {
                    "stable_entity_key": _STABLE_KEY_B,
                    "entity_type": "java_method",
                    "qualified_name": "Baz.qux",
                    "file_path": "src/Baz.java",
                },
            ],
            gold_edges=[
                {
                    "source_key": _STABLE_KEY_A,
                    "target_key": _STABLE_KEY_B,
                    "relation_type": "CALLS_METHOD",
                    "indexed_in_system": False,
                }
            ],
            chain_complete=False,
            provenance={
                "source_files": ["src/Foo.java", "src/Baz.java"],
                "generation_method": "manual_code_inspection",
                "created_at": "2026-01-15T10:00:00Z",
            },
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        chain_errors = [
            e for e in errors if e.rule == "edge_indexed_chain_complete"
        ]
        assert len(chain_errors) == 0


class TestPartialAnswerableRequiresUnindexedEdge:
    """Rule 13: system_answerable='partial' requires gold_edge with indexed_in_system=false."""

    def test_partial_without_unindexed_edge_fails(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            system_answerable="partial",
            gold_edges=[
                {
                    "source_key": _STABLE_KEY_A,
                    "target_key": _STABLE_KEY_B,
                    "relation_type": "CALLS_METHOD",
                    "indexed_in_system": True,
                }
            ],
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        partial_errors = [
            e for e in errors
            if e.rule == "partial_answerable_requires_unindexed_edge"
        ]
        assert len(partial_errors) == 1

    def test_partial_with_unindexed_edge_passes(self, tmp_path: Path) -> None:
        rec = _make_valid_record(
            system_answerable="partial",
            gold_edges=[
                {
                    "source_key": _STABLE_KEY_A,
                    "target_key": _STABLE_KEY_B,
                    "relation_type": "CALLS_METHOD",
                    "indexed_in_system": False,
                }
            ],
            chain_complete=False,
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        partial_errors = [
            e for e in errors
            if e.rule == "partial_answerable_requires_unindexed_edge"
        ]
        assert len(partial_errors) == 0


# ===================================================================
# Schema v1.2.0 negative tests (old-format data must fail)
# ===================================================================


class TestSchemaV120Negative:
    """Negative tests proving that old-format data fails validation
    under Schema v1.2.0."""

    def test_string_gold_entities_fail(self, tmp_path: Path) -> None:
        """String gold_entities must fail -- items must be objects."""
        rec = _make_valid_record(gold_entities=["SomeEntity"])
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("gold_entities" in e.field for e in schema_errors)

    def test_string_gold_files_fail(self, tmp_path: Path) -> None:
        """String gold_files must fail -- items must be objects."""
        rec = _make_valid_record(gold_files=["src/Main.java"])
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("gold_files" in e.field for e in schema_errors)

    def test_string_required_claims_fail(self, tmp_path: Path) -> None:
        """String required_claims must fail -- items must be objects."""
        rec = _make_valid_record(
            required_claims=["The API is at /api/users"]
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("required_claims" in e.field for e in schema_errors)

    def test_reviewed_accepted_gold_status_fails(self, tmp_path: Path) -> None:
        """'reviewed_accepted' is not a valid gold_status in v1.2.0."""
        rec = _make_valid_record(gold_status="reviewed_accepted")
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("gold_status" in e.field for e in schema_errors)

    def test_synthesis_evaluation_layer_fails(self, tmp_path: Path) -> None:
        """'synthesis' is not a valid evaluation_layer in v1.2.0."""
        rec = _make_valid_record(evaluation_layers=["synthesis"])
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("evaluation_layers" in e.field for e in schema_errors)

    def test_missing_stable_entity_key_in_gold_entities_fails(
        self, tmp_path: Path
    ) -> None:
        """gold_entities items without stable_entity_key must fail."""
        rec = _make_valid_record(
            gold_entities=[
                {
                    "entity_type": "java_method",
                    "qualified_name": "Foo.bar",
                    "file_path": "src/Foo.java",
                    "start_line": 10,
                    "end_line": 20,
                    "relevance": "must_recall",
                    # stable_entity_key intentionally missing
                }
            ]
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any(
            "stable_entity_key" in e.field or "stable_entity_key" in e.reason
            for e in schema_errors
        ), f"Expected stable_entity_key schema error, got: {[(e.field, e.reason) for e in schema_errors]}"

    def test_underscore_in_question_id_fails(self, tmp_path: Path) -> None:
        """question_id with underscores must fail -- only hyphens allowed."""
        rec = _make_valid_record(question_id="ruoyi_code_qa-0001")
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("question_id" in e.field for e in schema_errors)

    def test_old_answerable_field_fails(self, tmp_path: Path) -> None:
        """The old 'answerable' field is not in schema v1.2.0
        (replaced by source_answerable + system_answerable)."""
        rec = _make_valid_record()
        # Remove the new fields and add the old one
        del rec["source_answerable"]
        del rec["system_answerable"]
        rec["answerable"] = True
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        # Should get errors for: missing source_answerable, missing system_answerable,
        # and unexpected property 'answerable'
        assert any(
            "answerable" in e.field or "answerable" in e.reason
            or "source_answerable" in e.field or "source_answerable" in e.reason
            or "system_answerable" in e.field or "system_answerable" in e.reason
            for e in schema_errors
        ), f"Expected answerable-related schema error, got: {[(e.field, e.reason) for e in schema_errors]}"

    def test_string_special_sample_type_fails(self, tmp_path: Path) -> None:
        """special_sample_type items must be integers, not strings."""
        rec = _make_valid_record(
            special_sample_type=["distractor_entity", "same_name_entity"]
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("special_sample_type" in e.field for e in schema_errors)

    def test_string_gold_nodes_fail(self, tmp_path: Path) -> None:
        """String gold_nodes must fail -- items must be objects."""
        rec = _make_valid_record(gold_nodes=["POST /login", "SomeController"])
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        schema_errors = [e for e in errors if e.rule == "json_schema"]
        assert len(schema_errors) >= 1
        assert any("gold_nodes" in e.field for e in schema_errors)


# ===================================================================
# Rule 14: Language consistency
# ===================================================================


class TestLanguageConsistency:
    """Rule 14: question text should match declared language."""

    def test_chinese_question_with_zh_passes(self, tmp_path: Path) -> None:
        """A Chinese question with language='zh' should pass."""
        rec = _make_valid_record(
            language="zh",
            question="用户登录的接口定义在哪个控制器中？",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        lang_errors = [e for e in errors if e.rule == "language_consistency"]
        assert len(lang_errors) == 0

    def test_english_question_with_en_passes(self, tmp_path: Path) -> None:
        """An English question with language='en' should pass."""
        rec = _make_valid_record(
            language="en",
            question="Where is the user list API implemented?",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        lang_errors = [e for e in errors if e.rule == "language_consistency"]
        assert len(lang_errors) == 0

    def test_english_question_with_zh_fails(self, tmp_path: Path) -> None:
        """An English question with language='zh' should fail (obvious mismatch)."""
        rec = _make_valid_record(
            language="zh",
            question="Where is the user list API implemented?",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        lang_errors = [e for e in errors if e.rule == "language_consistency"]
        assert len(lang_errors) == 1
        assert "CJK" in lang_errors[0].reason

    def test_chinese_question_with_en_fails(self, tmp_path: Path) -> None:
        """A Chinese question with language='en' should fail (obvious mismatch)."""
        rec = _make_valid_record(
            language="en",
            question="用户登录的接口定义在哪个控制器中？该接口的HTTP方法是什么？",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        lang_errors = [e for e in errors if e.rule == "language_consistency"]
        assert len(lang_errors) == 1
        assert "CJK" in lang_errors[0].reason

    def test_mixed_with_proper_nouns_no_false_positive(
        self, tmp_path: Path
    ) -> None:
        """An English question mentioning CamelCase class names and API paths
        should not false-positive even if those tokens are stripped."""
        rec = _make_valid_record(
            language="en",
            question=(
                "Which controller handles SysUserController "
                "at /api/system/user for the list query?"
            ),
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        lang_errors = [e for e in errors if e.rule == "language_consistency"]
        assert len(lang_errors) == 0

    def test_empty_question_handled_gracefully(self, tmp_path: Path) -> None:
        """An empty question string should not crash the rule."""
        rec = _make_valid_record(
            language="zh",
            question="",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        lang_errors = [e for e in errors if e.rule == "language_consistency"]
        assert len(lang_errors) == 0


# ===================================================================
# Rule 15: Execution status / gold status consistency
# ===================================================================


class TestExecutionStatusGoldConsistency:
    """Rule 15: prepared_not_executed must not have verified gold_status."""

    def test_prepared_not_executed_with_machine_verified_fails(
        self, tmp_path: Path
    ) -> None:
        rec = _make_valid_record(
            execution_status="prepared_not_executed",
            gold_status="machine_verified",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        exec_errors = [
            e for e in errors if e.rule == "execution_status_gold_consistency"
        ]
        assert len(exec_errors) == 1
        assert "prepared_not_executed" in exec_errors[0].reason

    def test_prepared_not_executed_with_human_verified_fails(
        self, tmp_path: Path
    ) -> None:
        rec = _make_valid_record(
            execution_status="prepared_not_executed",
            gold_status="human_verified",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        exec_errors = [
            e for e in errors if e.rule == "execution_status_gold_consistency"
        ]
        assert len(exec_errors) == 1

    def test_prepared_not_executed_with_machine_proposed_passes(
        self, tmp_path: Path
    ) -> None:
        """machine_proposed is not a verified status, so this should pass."""
        rec = _make_valid_record(
            execution_status="prepared_not_executed",
            gold_status="machine_proposed",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        exec_errors = [
            e for e in errors if e.rule == "execution_status_gold_consistency"
        ]
        assert len(exec_errors) == 0

    def test_executable_with_machine_verified_passes(
        self, tmp_path: Path
    ) -> None:
        """Normal executable + machine_verified should pass."""
        rec = _make_valid_record(
            execution_status="executable",
            gold_status="machine_verified",
        )
        dataset_path = _write_jsonl(str(tmp_path), [rec])
        errors, total = validate_dataset(dataset_path, _SCHEMA_PATH)
        exec_errors = [
            e for e in errors if e.rule == "execution_status_gold_consistency"
        ]
        assert len(exec_errors) == 0
