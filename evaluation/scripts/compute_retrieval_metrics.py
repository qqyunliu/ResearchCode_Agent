#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute retrieval evaluation metrics from gold and prediction files.

Reads a gold-standard JSONL file and a predictions JSONL file, then computes
standard information-retrieval metrics: Recall@1, Recall@5, Recall@10, MRR
(Mean Reciprocal Rank), and zero-hit rate.

Results are reported overall and optionally grouped by a metadata field
(language, difficulty, answerable, or task_type).

Usage:
    python compute_retrieval_metrics.py --gold GOLD --predictions PRED [--output OUT] [--group-by FIELD]

Input format:
    Gold file (JSONL, one record per line):
        {
            "question_id": "ruoyi-qa-0001",
            "language": "zh",
            "difficulty": "medium",
            "answerable": true,
            "task_type": "CODE_QA",
            "gold_entities": [
                {"entity_key": "abc123...", "relevance": "must_recall"},
                {"entity_key": "def456...", "relevance": "acceptable_alternative"}
            ]
        }

    Predictions file (JSONL, one record per line):
        {
            "question_id": "ruoyi-qa-0001",
            "hits": [
                {"entity_key": "abc123...", "score": 0.95},
                {"entity_key": "xyz789...", "score": 0.80}
            ]
        }

Output:
    JSON object with "overall" metrics and optional "groups" breakdown.

Exit codes:
    0  Success.
    1  Input error (missing files, format mismatch, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


# ===================================================================
# Core metric computation
# ===================================================================


def _compute_single_query_metrics(
    must_recall_keys: set[str],
    hit_keys: list[str],
) -> dict[str, float]:
    """Compute retrieval metrics for a single query.

    Parameters
    ----------
    must_recall_keys:
        Set of entity keys that *must* be retrieved.
    hit_keys:
        Ordered list of retrieved entity keys (highest score first).

    Returns
    -------
    dict with keys: recall_at_1, recall_at_5, recall_at_10, reciprocal_rank,
    zero_hit (1.0 if zero must_recall hits, else 0.0).
    """
    if not must_recall_keys:
        # No must_recall entities -- metrics are undefined; report as N/A (None).
        return {
            "recall_at_1": None,  # type: ignore[dict-item]
            "recall_at_5": None,  # type: ignore[dict-item]
            "recall_at_10": None,  # type: ignore[dict-item]
            "reciprocal_rank": None,  # type: ignore[dict-item]
            "zero_hit": None,  # type: ignore[dict-item]
        }

    recall_at_1 = 1.0 if any(k in must_recall_keys for k in hit_keys[:1]) else 0.0
    recall_at_5 = 1.0 if any(k in must_recall_keys for k in hit_keys[:5]) else 0.0
    recall_at_10 = 1.0 if any(k in must_recall_keys for k in hit_keys[:10]) else 0.0

    # MRR: reciprocal rank of the first must_recall hit
    reciprocal_rank = 0.0
    for rank, key in enumerate(hit_keys, start=1):
        if key in must_recall_keys:
            reciprocal_rank = 1.0 / rank
            break

    # Zero-hit: did we get zero must_recall entities in all results?
    any_hit = any(k in must_recall_keys for k in hit_keys)
    zero_hit = 0.0 if any_hit else 1.0

    return {
        "recall_at_1": recall_at_1,
        "recall_at_5": recall_at_5,
        "recall_at_10": recall_at_10,
        "reciprocal_rank": reciprocal_rank,
        "zero_hit": zero_hit,
    }


def _aggregate_metrics(
    per_query: list[dict[str, float | None]],
) -> dict[str, float | int]:
    """Aggregate per-query metrics into summary statistics.

    Only queries with defined (non-None) metrics are included.
    """
    if not per_query:
        return {
            "num_queries": 0,
            "recall_at_1": None,  # type: ignore[dict-item]
            "recall_at_5": None,  # type: ignore[dict-item]
            "recall_at_10": None,  # type: ignore[dict-item]
            "mrr": None,  # type: ignore[dict-item]
            "zero_hit_rate": None,  # type: ignore[dict-item]
        }

    def _safe_mean(values: list[float | None]) -> float | None:
        valid = [v for v in values if v is not None]
        if not valid:
            return None
        return sum(valid) / len(valid)

    return {
        "num_queries": len(per_query),
        "recall_at_1": _safe_mean([q["recall_at_1"] for q in per_query]),
        "recall_at_5": _safe_mean([q["recall_at_5"] for q in per_query]),
        "recall_at_10": _safe_mean([q["recall_at_10"] for q in per_query]),
        "mrr": _safe_mean([q["reciprocal_rank"] for q in per_query]),
        "zero_hit_rate": _safe_mean([q["zero_hit"] for q in per_query]),
    }


# ===================================================================
# File loading
# ===================================================================


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    """Load a JSONL file, returning a list of parsed records."""
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_number, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                print(
                    f"Warning: skipping line {line_number} in {path}: {exc}",
                    file=sys.stderr,
                )
    return records


def _extract_must_recall_keys(gold_record: dict[str, Any]) -> set[str]:
    """Extract must_recall entity keys from a gold record.

    Supports both ``entity_key`` and ``stable_entity_key`` field names.
    """
    keys: set[str] = set()
    for entity in gold_record.get("gold_entities") or []:
        if entity.get("relevance") == "must_recall":
            key = entity.get("entity_key") or entity.get("stable_entity_key")
            if key:
                keys.add(key)
    return keys


def _extract_hit_keys(pred_record: dict[str, Any]) -> list[str]:
    """Extract ordered entity keys from a prediction record."""
    return [
        h["entity_key"]
        for h in (pred_record.get("hits") or [])
        if "entity_key" in h
    ]


# ===================================================================
# Main computation pipeline
# ===================================================================


def compute_metrics(
    gold_path: str,
    predictions_path: str,
    group_by: str | None = None,
) -> dict[str, Any]:
    """Compute retrieval metrics and return a structured result dict.

    Parameters
    ----------
    gold_path:
        Path to the gold-standard JSONL file.
    predictions_path:
        Path to the predictions JSONL file.
    group_by:
        Optional metadata field to group results by (e.g. "language").

    Returns
    -------
    dict with "overall" metrics and optional "groups".
    """
    gold_records = _load_jsonl(gold_path)
    pred_records = _load_jsonl(predictions_path)

    # Index predictions by question_id
    pred_by_qid: dict[str, dict[str, Any]] = {}
    for rec in pred_records:
        qid = rec.get("question_id")
        if qid:
            pred_by_qid[qid] = rec

    # Compute per-query metrics
    all_query_metrics: list[dict[str, float | None]] = []
    # For grouping, store (group_value, query_metrics) pairs
    grouped: dict[str, list[dict[str, float | None]]] = {}
    answerable_metrics: list[dict[str, float | None]] = []
    unanswerable_metrics: list[dict[str, float | None]] = []

    unmatched_count = 0

    for gold_rec in gold_records:
        qid = gold_rec.get("question_id")
        if not qid:
            continue

        pred_rec = pred_by_qid.get(qid)
        if pred_rec is None:
            # No prediction for this gold question -- treat as empty retrieval
            hit_keys: list[str] = []
            unmatched_count += 1
        else:
            hit_keys = _extract_hit_keys(pred_rec)

        must_recall = _extract_must_recall_keys(gold_rec)
        qm = _compute_single_query_metrics(must_recall, hit_keys)
        all_query_metrics.append(qm)

        # Separate by answerable
        is_answerable = gold_rec.get("answerable", True)
        if is_answerable:
            answerable_metrics.append(qm)
        else:
            unanswerable_metrics.append(qm)

        # Grouping
        if group_by:
            group_val = str(gold_rec.get(group_by, "<missing>"))
            grouped.setdefault(group_val, []).append(qm)

    result: dict[str, Any] = {
        "overall": _aggregate_metrics(all_query_metrics),
        "answerable": _aggregate_metrics(answerable_metrics),
        "unanswerable": _aggregate_metrics(unanswerable_metrics),
        "metadata": {
            "gold_file": gold_path,
            "predictions_file": predictions_path,
            "total_gold_questions": len(gold_records),
            "total_predictions": len(pred_records),
            "unmatched_gold_questions": unmatched_count,
        },
    }

    if group_by:
        result["groups"] = {
            group_val: _aggregate_metrics(metrics_list)
            for group_val, metrics_list in sorted(grouped.items())
        }
        result["metadata"]["group_by"] = group_by

    return result


# ===================================================================
# CLI
# ===================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute retrieval evaluation metrics (Recall@K, MRR, zero-hit "
            "rate) from gold-standard and prediction JSONL files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  Success.\n"
            "  1  Input error or computation failure.\n"
        ),
    )
    parser.add_argument(
        "--gold",
        required=True,
        help="Path to the gold-standard JSONL file.",
    )
    parser.add_argument(
        "--predictions",
        required=True,
        help="Path to the predictions JSONL file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Path to write JSON output. Defaults to stdout."
        ),
    )
    parser.add_argument(
        "--group-by",
        choices=["language", "difficulty", "answerable", "task_type"],
        default=None,
        help="Group metrics by a metadata field from the gold file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    gold_path: str = args.gold
    pred_path: str = args.predictions
    output_path: str | None = args.output
    group_by: str | None = args.group_by

    # Validate input files exist
    if not os.path.isfile(gold_path):
        print(f"Error: gold file not found: {gold_path}", file=sys.stderr)
        return 1
    if not os.path.isfile(pred_path):
        print(f"Error: predictions file not found: {pred_path}", file=sys.stderr)
        return 1

    result = compute_metrics(gold_path, pred_path, group_by)

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
            fh.write("\n")
        print(f"Metrics written to {output_path}", file=sys.stderr)
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
