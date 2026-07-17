#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for compute_retrieval_metrics.py.

Creates temporary gold and prediction JSONL files, runs the metric
computation, and asserts on the resulting metric values.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from compute_retrieval_metrics import (  # noqa: E402
    compute_metrics,
    main,
)


# ===================================================================
# Helpers
# ===================================================================


def _write_jsonl(tmp_dir: Path, filename: str, records: list[dict]) -> str:
    """Write records to a JSONL file and return its path."""
    path = tmp_dir / filename
    with open(str(path), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return str(path)


def _make_gold_record(
    question_id: str,
    must_recall_keys: list[str],
    language: str = "en",
    difficulty: str = "medium",
    answerable: bool = True,
    task_type: str = "CODE_QA",
) -> dict:
    """Build a gold record with the given must_recall entity keys."""
    entities = [
        {"entity_key": k, "relevance": "must_recall"} for k in must_recall_keys
    ]
    return {
        "question_id": question_id,
        "language": language,
        "difficulty": difficulty,
        "answerable": answerable,
        "task_type": task_type,
        "gold_entities": entities,
    }


def _make_pred_record(
    question_id: str,
    hit_keys: list[str],
) -> dict:
    """Build a prediction record with ordered hit entity keys."""
    hits = [
        {"entity_key": k, "score": 1.0 - i * 0.1}
        for i, k in enumerate(hit_keys)
    ]
    return {
        "question_id": question_id,
        "hits": hits,
    }


# ===================================================================
# Tests
# ===================================================================


class TestPerfectRetrieval:
    """All must_recall entities appear at rank 1."""

    def test_perfect_retrieval(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["entity_A"]),
            _make_gold_record("q2", ["entity_B"]),
            _make_gold_record("q3", ["entity_C"]),
        ]
        preds = [
            _make_pred_record("q1", ["entity_A", "entity_X", "entity_Y"]),
            _make_pred_record("q2", ["entity_B", "entity_X"]),
            _make_pred_record("q3", ["entity_C"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)
        overall = result["overall"]

        assert overall["recall_at_1"] == pytest.approx(1.0)
        assert overall["recall_at_5"] == pytest.approx(1.0)
        assert overall["recall_at_10"] == pytest.approx(1.0)
        assert overall["mrr"] == pytest.approx(1.0)
        assert overall["zero_hit_rate"] == pytest.approx(0.0)


class TestZeroRetrieval:
    """No must_recall entities are retrieved at all."""

    def test_zero_retrieval(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["entity_A"]),
            _make_gold_record("q2", ["entity_B"]),
        ]
        preds = [
            _make_pred_record("q1", ["entity_X", "entity_Y", "entity_Z"]),
            _make_pred_record("q2", ["entity_W"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)
        overall = result["overall"]

        assert overall["recall_at_1"] == pytest.approx(0.0)
        assert overall["recall_at_5"] == pytest.approx(0.0)
        assert overall["recall_at_10"] == pytest.approx(0.0)
        assert overall["mrr"] == pytest.approx(0.0)
        assert overall["zero_hit_rate"] == pytest.approx(1.0)


class TestPartialRetrieval:
    """Some queries retrieve must_recall entities, others do not."""

    def test_partial_retrieval(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["entity_A"]),
            _make_gold_record("q2", ["entity_B"]),
        ]
        preds = [
            # q1: entity_A at rank 3
            _make_pred_record("q1", ["entity_X", "entity_Y", "entity_A"]),
            # q2: entity_B not retrieved
            _make_pred_record("q2", ["entity_W", "entity_Z"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)
        overall = result["overall"]

        # Recall@1: q1 miss (rank 3), q2 miss -> 0/2 = 0.0
        assert overall["recall_at_1"] == pytest.approx(0.0)
        # Recall@5: q1 hit (rank 3 <= 5), q2 miss -> 1/2 = 0.5
        assert overall["recall_at_5"] == pytest.approx(0.5)
        # Recall@10: q1 hit (rank 3 <= 10), q2 miss -> 1/2 = 0.5
        assert overall["recall_at_10"] == pytest.approx(0.5)
        # MRR: q1 = 1/3, q2 = 0 -> mean = (1/3) / 2
        assert overall["mrr"] == pytest.approx(1.0 / 6.0)
        # Zero-hit: q1 has hit, q2 zero hit -> 1/2 = 0.5
        assert overall["zero_hit_rate"] == pytest.approx(0.5)


class TestGrouping:
    """Metrics can be grouped by a metadata field."""

    def test_group_by_language(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["eA"], language="zh"),
            _make_gold_record("q2", ["eB"], language="en"),
            _make_gold_record("q3", ["eC"], language="zh"),
        ]
        preds = [
            # q1 (zh): perfect
            _make_pred_record("q1", ["eA"]),
            # q2 (en): miss
            _make_pred_record("q2", ["eX"]),
            # q3 (zh): perfect
            _make_pred_record("q3", ["eC"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path, group_by="language")

        assert "groups" in result
        groups = result["groups"]

        # Chinese: 2 queries, both perfect
        assert groups["zh"]["recall_at_1"] == pytest.approx(1.0)
        assert groups["zh"]["num_queries"] == 2

        # English: 1 query, miss
        assert groups["en"]["recall_at_1"] == pytest.approx(0.0)
        assert groups["en"]["num_queries"] == 1

    def test_group_by_difficulty(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["eA"], difficulty="easy"),
            _make_gold_record("q2", ["eB"], difficulty="hard"),
        ]
        preds = [
            _make_pred_record("q1", ["eA"]),
            _make_pred_record("q2", ["eX"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path, group_by="difficulty")
        groups = result["groups"]

        assert groups["easy"]["recall_at_1"] == pytest.approx(1.0)
        assert groups["hard"]["recall_at_1"] == pytest.approx(0.0)

    def test_group_by_task_type(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["eA"], task_type="CODE_QA"),
            _make_gold_record("q2", ["eB"], task_type="TRACE_CHAIN"),
        ]
        preds = [
            _make_pred_record("q1", ["eA"]),
            _make_pred_record("q2", ["eB"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path, group_by="task_type")
        groups = result["groups"]

        assert groups["CODE_QA"]["recall_at_1"] == pytest.approx(1.0)
        assert groups["TRACE_CHAIN"]["recall_at_1"] == pytest.approx(1.0)


class TestEmptyPredictions:
    """No predictions file entries -- all queries should have zero hits."""

    def test_empty_predictions(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["entity_A"]),
            _make_gold_record("q2", ["entity_B"]),
        ]
        preds: list[dict] = []
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)
        overall = result["overall"]

        assert overall["recall_at_1"] == pytest.approx(0.0)
        assert overall["recall_at_5"] == pytest.approx(0.0)
        assert overall["recall_at_10"] == pytest.approx(0.0)
        assert overall["mrr"] == pytest.approx(0.0)
        assert overall["zero_hit_rate"] == pytest.approx(1.0)
        assert result["metadata"]["unmatched_gold_questions"] == 2


class TestAnswerableFalse:
    """answerable=false queries should be reported separately."""

    def test_answerable_false_separate(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", ["eA"], answerable=True),
            # answerable=false with no must_recall entities
            _make_gold_record("q2", [], answerable=False),
            _make_gold_record("q3", ["eC"], answerable=True),
        ]
        preds = [
            _make_pred_record("q1", ["eA"]),
            _make_pred_record("q2", ["eX"]),
            _make_pred_record("q3", ["eY"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)

        # Answerable section
        ans = result["answerable"]
        assert ans["num_queries"] == 2
        # q1: perfect, q3: miss
        assert ans["recall_at_1"] == pytest.approx(0.5)

        # Unanswerable section
        unans = result["unanswerable"]
        assert unans["num_queries"] == 1
        # q2 has no must_recall entities, so metrics are None
        assert unans["recall_at_1"] is None

    def test_all_unanswerable(self, tmp_path: Path) -> None:
        gold = [
            _make_gold_record("q1", [], answerable=False),
            _make_gold_record("q2", [], answerable=False),
        ]
        preds = [
            _make_pred_record("q1", ["eX"]),
            _make_pred_record("q2", ["eY"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)

        assert result["answerable"]["num_queries"] == 0
        assert result["unanswerable"]["num_queries"] == 2
        assert result["unanswerable"]["recall_at_1"] is None


class TestCLIMain:
    """Test the CLI entry point."""

    def test_cli_help(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_cli_output_to_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        gold = [_make_gold_record("q1", ["eA"])]
        preds = [_make_pred_record("q1", ["eA"])]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        exit_code = main(["--gold", gold_path, "--predictions", pred_path])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["overall"]["recall_at_1"] == pytest.approx(1.0)

    def test_cli_output_to_file(self, tmp_path: Path) -> None:
        gold = [_make_gold_record("q1", ["eA"])]
        preds = [_make_pred_record("q1", ["eA"])]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)
        output_path = str(tmp_path / "result.json")

        exit_code = main([
            "--gold", gold_path,
            "--predictions", pred_path,
            "--output", output_path,
        ])
        assert exit_code == 0
        assert os.path.isfile(output_path)

        with open(output_path, "r", encoding="utf-8") as fh:
            output = json.load(fh)
        assert output["overall"]["recall_at_1"] == pytest.approx(1.0)

    def test_cli_group_by(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        gold = [
            _make_gold_record("q1", ["eA"], language="zh"),
            _make_gold_record("q2", ["eB"], language="en"),
        ]
        preds = [
            _make_pred_record("q1", ["eA"]),
            _make_pred_record("q2", ["eX"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        exit_code = main([
            "--gold", gold_path,
            "--predictions", pred_path,
            "--group-by", "language",
        ])
        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "groups" in output
        assert output["groups"]["zh"]["recall_at_1"] == pytest.approx(1.0)
        assert output["groups"]["en"]["recall_at_1"] == pytest.approx(0.0)

    def test_cli_missing_gold_file(self, tmp_path: Path) -> None:
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", [])
        exit_code = main([
            "--gold", str(tmp_path / "nonexistent.jsonl"),
            "--predictions", pred_path,
        ])
        assert exit_code == 1

    def test_cli_missing_pred_file(self, tmp_path: Path) -> None:
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", [])
        exit_code = main([
            "--gold", gold_path,
            "--predictions", str(tmp_path / "nonexistent.jsonl"),
        ])
        assert exit_code == 1


class TestStableEntityKey:
    """Ensure stable_entity_key field name is also supported."""

    def test_stable_entity_key_matching(self, tmp_path: Path) -> None:
        gold = [
            {
                "question_id": "q1",
                "language": "en",
                "difficulty": "easy",
                "answerable": True,
                "task_type": "CODE_QA",
                "gold_entities": [
                    {
                        "stable_entity_key": "stable_key_1",
                        "relevance": "must_recall",
                    }
                ],
            }
        ]
        preds = [
            _make_pred_record("q1", ["stable_key_1"])
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)
        assert result["overall"]["recall_at_1"] == pytest.approx(1.0)


class TestMultipleMustRecall:
    """Test with multiple must_recall entities per query."""

    def test_any_must_recall_hit_counts(self, tmp_path: Path) -> None:
        """Recall@K is satisfied if ANY must_recall entity appears in top-K."""
        gold = [
            _make_gold_record("q1", ["eA", "eB", "eC"]),
        ]
        # Only eC is retrieved, at rank 2
        preds = [
            _make_pred_record("q1", ["eX", "eC", "eY"]),
        ]
        gold_path = _write_jsonl(tmp_path, "gold.jsonl", gold)
        pred_path = _write_jsonl(tmp_path, "pred.jsonl", preds)

        result = compute_metrics(gold_path, pred_path)
        overall = result["overall"]

        assert overall["recall_at_1"] == pytest.approx(0.0)  # eC at rank 2
        assert overall["recall_at_5"] == pytest.approx(1.0)  # eC at rank 2 <= 5
        assert overall["mrr"] == pytest.approx(0.5)  # 1/2
