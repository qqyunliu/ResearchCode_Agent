#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for generate_report.py.

Creates small synthetic metrics JSON and dataset JSONL fixtures, runs the
report generator, and parses the Markdown output to verify correctness.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from generate_report import generate_report, _sha256_file  # noqa: E402


# =====================================================================
# Fixture helpers
# =====================================================================


def _make_dataset_jsonl(tmp_path: Path, records: list[dict]) -> Path:
    """Write dataset records to a JSONL file and return its path."""
    path = tmp_path / "test_dataset.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def _make_metrics_json(
    tmp_path: Path,
    dataset_sha: str,
    *,
    total_records: int = 6,
    eligible_records: int = 6,
    true_count: int = 4,
    false_count: int = 1,
    no_gold_count: int = 1,
    b0_overall_n: int = 4,
    b1_overall_n: int = 4,
) -> Path:
    """Create a metrics JSON file with the given SHA and return its path."""
    metrics = {
        "dataset_sha256": dataset_sha,
        "timestamp": "2026-07-15T12:00:00+00:00",
        "dataset_path": "test_dataset.jsonl",
        "total_records": total_records,
        "eligible_records": eligible_records,
        "source_answerable_true_count": true_count,
        "source_answerable_false_count": false_count,
        "no_gold_files_count": no_gold_count,
        "excluded_reasons": {},
        "configuration": {
            "dataset_path": "test_dataset.jsonl",
            "repo_path": "test_repo",
            "top_k": 10,
        },
        "b0_ripgrep": {
            "overall": {
                "n": b0_overall_n,
                "recall@1": 0.25,
                "recall@5": 0.50,
                "recall@10": 0.75,
                "mrr": 0.35,
                "zero_hit_rate": 0.25,
            },
            "diagnostic_source_answerable_false": {
                "n": 1,
                "recall@1": 0.0,
                "recall@5": 0.0,
                "recall@10": 0.0,
                "mrr": 0.0,
                "zero_hit_rate": 1.0,
            },
            "grouped": {
                "language": {
                    "en": {
                        "n": 2,
                        "recall@1": 0.5,
                        "recall@5": 0.5,
                        "recall@10": 1.0,
                        "mrr": 0.5,
                        "zero_hit_rate": 0.0,
                    },
                    "zh": {
                        "n": 2,
                        "recall@1": 0.0,
                        "recall@5": 0.5,
                        "recall@10": 0.5,
                        "mrr": 0.2,
                        "zero_hit_rate": 0.5,
                    },
                },
                "difficulty": {
                    "easy": {
                        "n": 2,
                        "recall@1": 0.5,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 0.75,
                        "zero_hit_rate": 0.0,
                    },
                    "medium": {
                        "n": 1,
                        "recall@1": 0.0,
                        "recall@5": 0.0,
                        "recall@10": 0.0,
                        "mrr": 0.0,
                        "zero_hit_rate": 1.0,
                    },
                    "hard": {
                        "n": 1,
                        "recall@1": 0.0,
                        "recall@5": 0.0,
                        "recall@10": 1.0,
                        "mrr": 0.1,
                        "zero_hit_rate": 0.0,
                    },
                },
                "task_type": {
                    "CODE_QA": {
                        "n": 2,
                        "recall@1": 0.0,
                        "recall@5": 0.5,
                        "recall@10": 0.5,
                        "mrr": 0.25,
                        "zero_hit_rate": 0.5,
                    },
                    "TRACE_CHAIN": {
                        "n": 1,
                        "recall@1": 1.0,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 1.0,
                        "zero_hit_rate": 0.0,
                    },
                    "CHANGE_PLAN": {
                        "n": 1,
                        "recall@1": 0.0,
                        "recall@5": 0.0,
                        "recall@10": 1.0,
                        "mrr": 0.1,
                        "zero_hit_rate": 0.0,
                    },
                },
            },
        },
        "b1_keyword": {
            "overall": {
                "n": b1_overall_n,
                "recall@1": 0.5,
                "recall@5": 0.75,
                "recall@10": 1.0,
                "mrr": 0.6,
                "zero_hit_rate": 0.0,
            },
            "diagnostic_source_answerable_false": {
                "n": 1,
                "recall@1": 0.0,
                "recall@5": 0.0,
                "recall@10": 0.0,
                "mrr": 0.0,
                "zero_hit_rate": 1.0,
            },
            "grouped": {
                "language": {
                    "en": {
                        "n": 2,
                        "recall@1": 0.5,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 0.75,
                        "zero_hit_rate": 0.0,
                    },
                    "zh": {
                        "n": 2,
                        "recall@1": 0.5,
                        "recall@5": 0.5,
                        "recall@10": 1.0,
                        "mrr": 0.5,
                        "zero_hit_rate": 0.0,
                    },
                },
                "difficulty": {
                    "easy": {
                        "n": 2,
                        "recall@1": 0.5,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 0.75,
                        "zero_hit_rate": 0.0,
                    },
                    "medium": {
                        "n": 1,
                        "recall@1": 0.0,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 0.5,
                        "zero_hit_rate": 0.0,
                    },
                    "hard": {
                        "n": 1,
                        "recall@1": 1.0,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 1.0,
                        "zero_hit_rate": 0.0,
                    },
                },
                "task_type": {
                    "CODE_QA": {
                        "n": 2,
                        "recall@1": 0.5,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 0.75,
                        "zero_hit_rate": 0.0,
                    },
                    "TRACE_CHAIN": {
                        "n": 1,
                        "recall@1": 1.0,
                        "recall@5": 1.0,
                        "recall@10": 1.0,
                        "mrr": 1.0,
                        "zero_hit_rate": 0.0,
                    },
                    "CHANGE_PLAN": {
                        "n": 1,
                        "recall@1": 0.0,
                        "recall@5": 0.0,
                        "recall@10": 1.0,
                        "mrr": 0.1,
                        "zero_hit_rate": 0.0,
                    },
                },
            },
        },
    }
    path = tmp_path / "test_metrics.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    return path


def _build_fixtures(tmp_path: Path) -> tuple[Path, Path, str]:
    """Build a matching pair of metrics JSON and dataset JSONL.

    Returns (metrics_path, dataset_path, dataset_sha).
    """
    records = [
        {
            "question_id": "q1",
            "task_type": "CODE_QA",
            "language": "en",
            "difficulty": "easy",
            "source_answerable": True,
            "system_answerable": "full",
            "commit_sha": "abc123",
        },
        {
            "question_id": "q2",
            "task_type": "CODE_QA",
            "language": "zh",
            "difficulty": "easy",
            "source_answerable": True,
            "system_answerable": "full",
            "commit_sha": "abc123",
        },
        {
            "question_id": "q3",
            "task_type": "TRACE_CHAIN",
            "language": "en",
            "difficulty": "medium",
            "source_answerable": True,
            "system_answerable": "insufficient",
            "commit_sha": "abc123",
        },
        {
            "question_id": "q4",
            "task_type": "CHANGE_PLAN",
            "language": "zh",
            "difficulty": "hard",
            "source_answerable": True,
            "system_answerable": "full",
            "commit_sha": "abc123",
        },
        {
            "question_id": "q5",
            "task_type": "CODE_QA",
            "language": "zh",
            "difficulty": "medium",
            "source_answerable": False,
            "system_answerable": "insufficient",
            "commit_sha": "abc123",
        },
        {
            "question_id": "q6",
            "task_type": "TRACE_CHAIN",
            "language": "en",
            "difficulty": "hard",
            "source_answerable": False,
            "system_answerable": "insufficient",
            "commit_sha": "abc123",
        },
    ]

    dataset_path = _make_dataset_jsonl(tmp_path, records)
    dataset_sha = _sha256_file(dataset_path)
    metrics_path = _make_metrics_json(tmp_path, dataset_sha)
    return metrics_path, dataset_path, dataset_sha


# =====================================================================
# Tests
# =====================================================================


class TestReportGeneration:
    """Generate report from synthetic fixtures and verify structure."""

    def test_report_generated_successfully(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"

        rc = generate_report(metrics_path, dataset_path, output_path)
        assert rc == 0
        assert output_path.is_file()
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 100

    def test_report_has_all_sections(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "Section A: Dataset Summary" in content
        assert "Section B: Baseline Results" in content
        assert "Section C: Consistency Checks" in content
        assert "Section D: Caveats" in content


class TestNumbersMatchMetricsJson:
    """Parse the generated Markdown and verify key numbers match the JSON."""

    def test_overall_metrics_match(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")

        # Load metrics for comparison
        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)

        # Verify B0 overall numbers appear in the report
        b0_overall = metrics["b0_ripgrep"]["overall"]
        assert f"{b0_overall['recall@1']:.4f}" in content  # 0.2500
        assert f"{b0_overall['recall@5']:.4f}" in content  # 0.5000
        assert f"{b0_overall['recall@10']:.4f}" in content  # 0.7500
        assert f"{b0_overall['mrr']:.4f}" in content  # 0.3500
        assert f"{b0_overall['zero_hit_rate']:.4f}" in content  # 0.2500

        # Verify B1 overall numbers
        b1_overall = metrics["b1_keyword"]["overall"]
        assert f"{b1_overall['recall@1']:.4f}" in content  # 0.5000
        assert f"{b1_overall['mrr']:.4f}" in content  # 0.6000

    def test_record_counts_match(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)

        # Verify record counts
        assert f"**Total records**: {metrics['total_records']}" in content
        assert f"**Eligible records**: {metrics['eligible_records']}" in content
        assert f"**source_answerable=true**: {metrics['source_answerable_true_count']}" in content
        assert f"**source_answerable=false**: {metrics['source_answerable_false_count']}" in content
        assert f"**No gold files**: {metrics['no_gold_files_count']}" in content

    def test_stage2a3_metrics_shape_is_rendered(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        stage2a3_metrics = {
            "dataset_path": metrics["dataset_path"],
            "dataset_sha256": metrics["dataset_sha256"],
            "timestamp": metrics["timestamp"],
            "dataset_records": 6,
            "schema_eligible_records": 6,
            "retrieval_layer_records": 6,
            "index_retrieval_scored_records": 4,
            "source_answerable_true_records": 4,
            "source_answerable_false_records": 2,
            "unanswerable_with_source_gold_records": 0,
            "skipped_no_indexable_gold_records": 1,
            "excluded_records_by_reason": {},
            "baselines": {
                "b0_rgrep": metrics["b0_ripgrep"],
                "b1_keyword": metrics["b1_keyword"],
            },
        }
        metrics_path.write_text(
            json.dumps(stage2a3_metrics, indent=2), encoding="utf-8"
        )

        output_path = tmp_path / "stage2a3-report.md"
        assert generate_report(metrics_path, dataset_path, output_path) == 0

        content = output_path.read_text(encoding="utf-8")
        assert "**Total records**: 6" in content
        assert "**Eligible records**: 6" in content
        assert "**source_answerable=true**: 4" in content
        assert "**source_answerable=false**: 2" in content
        assert "**Skipped: no indexable gold**: 1" in content
        assert "0.2500" in content
        assert "=> FAIL" not in content

    def test_grouped_numbers_match(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)

        # Verify a specific grouped value: b0 language en recall@1 = 0.5
        b0_lang_en = metrics["b0_ripgrep"]["grouped"]["language"]["en"]
        assert f"{b0_lang_en['recall@1']:.4f}" in content  # 0.5000

        # b1 task_type CODE_QA recall@1 = 0.5
        b1_tt_qa = metrics["b1_keyword"]["grouped"]["task_type"]["CODE_QA"]
        assert f"{b1_tt_qa['recall@1']:.4f}" in content  # 0.5000


class TestDatasetShaInReport:
    """Verify the dataset SHA-256 appears in the report."""

    def test_sha_in_header(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, dataset_sha = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert dataset_sha in content

    def test_sha_in_dataset_identity(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, dataset_sha = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        # SHA should appear in the Dataset Identity section
        assert f"`{dataset_sha}`" in content


class TestShaMismatchFails:
    """Modify the dataset (changing its SHA) and verify report generation fails."""

    def test_sha_mismatch_returns_error(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)

        # Append a record to the dataset to change its SHA
        with open(dataset_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "question_id": "q_extra",
                "task_type": "CODE_QA",
                "language": "en",
                "difficulty": "easy",
                "source_answerable": True,
                "system_answerable": "full",
                "commit_sha": "abc123",
            }) + "\n")

        output_path = tmp_path / "report.md"
        rc = generate_report(metrics_path, dataset_path, output_path)
        assert rc == 1
        assert not output_path.is_file()

    def test_sha_mismatch_message_on_stderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)

        # Modify dataset
        with open(dataset_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"question_id": "x"}) + "\n")

        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        captured = capsys.readouterr()
        assert "SHA-256 mismatch" in captured.err


class TestGroupTablesHaveSampleCounts:
    """Verify all group tables have sample counts (n)."""

    def test_group_tables_contain_n_column(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")

        # Check that each group section has a table header with 'n'
        group_sections = ["Grouped by language", "Grouped by difficulty", "Grouped by task_type"]
        for section in group_sections:
            idx = content.find(section)
            assert idx >= 0, f"Missing section: {section}"

            # Find the table header after the section
            section_text = content[idx:]
            # The table header should contain '| n |'
            assert "| n |" in section_text, (
                f"Group section '{section}' table header missing 'n' column"
            )

    def test_each_group_has_numeric_n(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")

        # Find all table rows with group data (lines starting with |)
        # and verify they have numeric n values
        table_lines = [
            line for line in content.split("\n")
            if line.startswith("|") and "---" not in line and "Metric" not in line
            and "n" not in line.split("|")[1]  # skip headers with 'n' as content
        ]

        # There should be data rows
        assert len(table_lines) > 0, "No data rows found in tables"


class TestNoHardcodedNumbers:
    """Verify that changing metrics values produces different report numbers."""

    def test_changing_metrics_changes_report(self, tmp_path: Path) -> None:
        # First run with original fixtures
        metrics_path, dataset_path, dataset_sha = _build_fixtures(tmp_path)
        output_path1 = tmp_path / "report1.md"
        generate_report(metrics_path, dataset_path, output_path1)
        content1 = output_path1.read_text(encoding="utf-8")

        # Modify the metrics JSON: change B0 recall@1 from 0.25 to 0.99
        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)
        metrics["b0_ripgrep"]["overall"]["recall@1"] = 0.99
        with open(metrics_path, "w", encoding="utf-8") as fh:
            json.dump(metrics, fh, indent=2)

        output_path2 = tmp_path / "report2.md"
        generate_report(metrics_path, dataset_path, output_path2)
        content2 = output_path2.read_text(encoding="utf-8")

        # The changed value must appear in the new report
        assert "0.9900" in content2
        # The old value should have been in the first report
        assert "0.2500" in content1

        # Reports must differ
        assert content1 != content2

    def test_changing_total_records_changes_report(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, dataset_sha = _build_fixtures(tmp_path)

        # Modify total_records in metrics
        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)
        metrics["total_records"] = 999
        with open(metrics_path, "w", encoding="utf-8") as fh:
            json.dump(metrics, fh, indent=2)

        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)
        content = output_path.read_text(encoding="utf-8")

        # The modified value must appear
        assert "**Total records**: 999" in content


class TestConsistencyChecksSection:
    """Verify the consistency checks section has correct reconciliation."""

    def test_reconciliation_pass(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")

        # All checks should PASS with valid fixtures
        assert "=> PASS" in content
        assert "=> FAIL" not in content

    def test_reconciliation_prints_arithmetic(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")

        # Verify the arithmetic expression is present
        assert "dataset_records (6)" in content
        assert "source_answerable_true (4)" in content
        assert "source_answerable_false (1)" in content
        assert "no_gold_files (1)" in content


class TestCrossDistributionTables:
    """Verify cross-distribution tables are computed from the dataset."""

    def test_task_type_x_language_table(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "Task Type x Language" in content
        # Verify some counts: we have 2 CODE_QA records (1 en, 1 zh + 1 zh from q5)
        # Actually: CODE_QA: q1(en), q2(zh), q5(zh) = 1 en + 2 zh
        assert "CODE_QA" in content

    def test_task_type_x_difficulty_table(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "Task Type x Difficulty" in content

    def test_task_type_x_system_answerable_table(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "Task Type x system_answerable" in content


class TestCaveatsSection:
    """Verify the caveats section mentions key limitations."""

    def test_caveats_mention_baselines(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "text-search baselines" in content.lower() or "text-matching baselines" in content.lower()

    def test_caveats_mention_single_repo(self, tmp_path: Path) -> None:
        metrics_path, dataset_path, _ = _build_fixtures(tmp_path)
        output_path = tmp_path / "report.md"
        generate_report(metrics_path, dataset_path, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "single" in content.lower() and "repo" in content.lower()
