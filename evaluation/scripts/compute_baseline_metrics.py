#!/usr/bin/env python3
"""Compute baseline metrics for the pilot evaluation.

**STATUS: legacy_debug_only**

This script was used during early-stage (Stage 2A.1) baseline computation.
It previously contained hardcoded default paths pointing to
annotations/proposed/ gold data, which could cause data contamination if
run against non-canonical datasets. The dangerous defaults have been
removed. All paths must now be provided explicitly as command-line arguments.

Use compute_canonical_metrics.py for the canonical pilot evaluation instead.

Handles the actual data formats:
- Gold: JSONL with gold_files (list of file paths) and gold_entities (list of strings)
- B0 predictions: JSONL with hits containing file_path
- B1 predictions: JSONL with hits containing file_path and entity info

Computes Recall@1/5/10, MRR, zero-hit rate at the file level,
plus grouped breakdowns by language, difficulty, task_type.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    text = path.read_text(encoding="utf-8")
    for line in text.strip().splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def compute_file_level_metrics(
    gold_records: list[dict[str, Any]],
    pred_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute file-level retrieval metrics.

    For each query, check if any of the top-K hits' file_path matches
    any of the gold_files.
    """
    pred_by_qid = {r["question_id"]: r for r in pred_records}

    per_query: list[dict[str, Any]] = []
    zero_hit_cases: list[dict[str, str]] = []

    for gold in gold_records:
        qid = gold["question_id"]
        gold_files = set(gold.get("gold_files", []))
        pred = pred_by_qid.get(qid)

        # Skip questions with no gold files (unanswerable)
        if not gold_files:
            per_query.append({
                "question_id": qid,
                "recall_at_1": None,
                "recall_at_5": None,
                "recall_at_10": None,
                "reciprocal_rank": None,
                "zero_hit": None,
                "skipped": True,
                "language": gold.get("language"),
                "difficulty": gold.get("difficulty"),
                "task_type": gold.get("task_type"),
                "answerable": gold.get("answerable", True),
            })
            continue

        hit_files = []
        if pred:
            hit_files = [h["file_path"] for h in pred.get("hits", [])]

        recall_at_1 = 1.0 if any(f in gold_files for f in hit_files[:1]) else 0.0
        recall_at_5 = 1.0 if any(f in gold_files for f in hit_files[:5]) else 0.0
        recall_at_10 = 1.0 if any(f in gold_files for f in hit_files[:10]) else 0.0

        rr = 0.0
        for rank, fp in enumerate(hit_files, 1):
            if fp in gold_files:
                rr = 1.0 / rank
                break

        any_hit = any(f in gold_files for f in hit_files)
        zero_hit = 0.0 if any_hit else 1.0

        entry = {
            "question_id": qid,
            "recall_at_1": recall_at_1,
            "recall_at_5": recall_at_5,
            "recall_at_10": recall_at_10,
            "reciprocal_rank": rr,
            "zero_hit": zero_hit,
            "skipped": False,
            "language": gold.get("language"),
            "difficulty": gold.get("difficulty"),
            "task_type": gold.get("task_type"),
            "answerable": gold.get("answerable", True),
            "num_hits": len(hit_files),
        }
        per_query.append(entry)

        if zero_hit > 0:
            zero_hit_cases.append({
                "question_id": qid,
                "query": pred.get("query", gold.get("question", "")) if pred else gold.get("question", ""),
                "gold_files": list(gold_files),
                "language": gold.get("language"),
                "difficulty": gold.get("difficulty"),
            })

    return {"per_query": per_query, "zero_hit_cases": zero_hit_cases}


def safe_mean(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 4)


def aggregate(per_query: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [q for q in per_query if not q.get("skipped")]
    if not valid:
        return {
            "num_queries": len(per_query),
            "num_evaluated": 0,
            "recall_at_1": None,
            "recall_at_5": None,
            "recall_at_10": None,
            "mrr": None,
            "zero_hit_rate": None,
        }
    return {
        "num_queries": len(per_query),
        "num_evaluated": len(valid),
        "recall_at_1": safe_mean([q["recall_at_1"] for q in valid]),
        "recall_at_5": safe_mean([q["recall_at_5"] for q in valid]),
        "recall_at_10": safe_mean([q["recall_at_10"] for q in valid]),
        "mrr": safe_mean([q["reciprocal_rank"] for q in valid]),
        "zero_hit_rate": safe_mean([q["zero_hit"] for q in valid]),
    }


def group_by_field(
    per_query: list[dict[str, Any]], field: str
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for q in per_query:
        val = str(q.get(field, "<missing>"))
        groups.setdefault(val, []).append(q)
    return {val: aggregate(items) for val, items in sorted(groups.items())}


def compute_execution_stats(
    pred_records: list[dict[str, Any]],
) -> dict[str, float]:
    times = [r.get("execution_time_seconds", 0) for r in pred_records]
    if not times:
        return {"mean_seconds": 0, "total_seconds": 0, "max_seconds": 0}
    return {
        "mean_seconds": round(sum(times) / len(times), 4),
        "total_seconds": round(sum(times), 4),
        "max_seconds": round(max(times), 4),
    }


def main() -> int:
    if len(sys.argv) < 5:
        print(
            "Usage: compute_baseline_metrics.py <gold.jsonl> <b0.jsonl> <b1.jsonl> <output.json>",
            file=sys.stderr,
        )
        print(
            "All four arguments are required. No default paths are provided "
            "to prevent accidental use of non-canonical gold data.",
            file=sys.stderr,
        )
        return 1

    gold_path = Path(sys.argv[1])
    b0_path = Path(sys.argv[2])
    b1_path = Path(sys.argv[3])
    output_path = Path(sys.argv[4])

    gold_records = load_jsonl(gold_path)
    b0_records = load_jsonl(b0_path)
    b1_records = load_jsonl(b1_path)

    # Compute metrics for both baselines
    b0_result = compute_file_level_metrics(gold_records, b0_records)
    b1_result = compute_file_level_metrics(gold_records, b1_records)

    # Aggregate
    b0_overall = aggregate(b0_result["per_query"])
    b1_overall = aggregate(b1_result["per_query"])

    # Grouped metrics
    b0_by_language = group_by_field(b0_result["per_query"], "language")
    b0_by_difficulty = group_by_field(b0_result["per_query"], "difficulty")
    b0_by_task_type = group_by_field(b0_result["per_query"], "task_type")

    b1_by_language = group_by_field(b1_result["per_query"], "language")
    b1_by_difficulty = group_by_field(b1_result["per_query"], "difficulty")
    b1_by_task_type = group_by_field(b1_result["per_query"], "task_type")

    # Execution stats
    b0_exec = compute_execution_stats(b0_records)
    b1_exec = compute_execution_stats(b1_records)

    # Answerable vs unanswerable
    b0_answerable = aggregate([q for q in b0_result["per_query"] if q.get("answerable") and not q.get("skipped")])
    b0_unanswerable = aggregate([q for q in b0_result["per_query"] if not q.get("answerable") and not q.get("skipped")])
    b1_answerable = aggregate([q for q in b1_result["per_query"] if q.get("answerable") and not q.get("skipped")])
    b1_unanswerable = aggregate([q for q in b1_result["per_query"] if not q.get("answerable") and not q.get("skipped")])

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dataset": {
            "total_questions": len(gold_records),
            "gold_file": str(gold_path),
        },
        "B0_ripgrep": {
            "description": "B0 baseline: ripgrep text search (token extraction + file-level grep)",
            "predictions_file": str(b0_path),
            "overall": b0_overall,
            "answerable": b0_answerable,
            "unanswerable": b0_unanswerable,
            "by_language": b0_by_language,
            "by_difficulty": b0_by_difficulty,
            "by_task_type": b0_by_task_type,
            "execution_stats": b0_exec,
            "zero_hit_cases": b0_result["zero_hit_cases"],
        },
        "B1_keyword": {
            "description": "B1 baseline: SQLite keyword search (token extraction + KeywordSearchService per-token)",
            "predictions_file": str(b1_path),
            "overall": b1_overall,
            "answerable": b1_answerable,
            "unanswerable": b1_unanswerable,
            "by_language": b1_by_language,
            "by_difficulty": b1_by_difficulty,
            "by_task_type": b1_by_task_type,
            "execution_stats": b1_exec,
            "scan_time_seconds": b1_records[0].get("scan_time_seconds") if b1_records else None,
            "entity_count": b1_records[0].get("entity_count") if b1_records else None,
            "zero_hit_cases": b1_result["zero_hit_cases"],
        },
        "notes": [
            "File-level matching: a hit is counted if any result file_path matches any gold_file.",
            "Questions with empty gold_files (unanswerable) are excluded from Recall/MRR computation.",
            "B0 uses ripgrep with token extraction from questions (min token length 3).",
            "B1 uses KeywordSearchService with per-token LIKE search, aggregated by file_path.",
            "Chinese questions often produce long tokens that don't match entity names, leading to zero hits in B1.",
        ],
    }

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Print summary to stderr
    print("=" * 60, file=sys.stderr)
    print("BASELINE EVALUATION SUMMARY", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    print(f"\nDataset: {len(gold_records)} questions", file=sys.stderr)
    print(f"Evaluated (with gold_files): {b0_overall['num_evaluated']}", file=sys.stderr)

    print(f"\n--- B0 (ripgrep) ---", file=sys.stderr)
    print(f"  Recall@1:  {b0_overall['recall_at_1']}", file=sys.stderr)
    print(f"  Recall@5:  {b0_overall['recall_at_5']}", file=sys.stderr)
    print(f"  Recall@10: {b0_overall['recall_at_10']}", file=sys.stderr)
    print(f"  MRR:       {b0_overall['mrr']}", file=sys.stderr)
    print(f"  Zero-hit:  {b0_overall['zero_hit_rate']}", file=sys.stderr)
    print(f"  Avg time:  {b0_exec['mean_seconds']}s", file=sys.stderr)

    print(f"\n--- B1 (keyword) ---", file=sys.stderr)
    print(f"  Recall@1:  {b1_overall['recall_at_1']}", file=sys.stderr)
    print(f"  Recall@5:  {b1_overall['recall_at_5']}", file=sys.stderr)
    print(f"  Recall@10: {b1_overall['recall_at_10']}", file=sys.stderr)
    print(f"  MRR:       {b1_overall['mrr']}", file=sys.stderr)
    print(f"  Zero-hit:  {b1_overall['zero_hit_rate']}", file=sys.stderr)
    print(f"  Avg time:  {b1_exec['mean_seconds']}s", file=sys.stderr)

    print(f"\nZero-hit cases (B0): {len(b0_result['zero_hit_cases'])}", file=sys.stderr)
    print(f"Zero-hit cases (B1): {len(b1_result['zero_hit_cases'])}", file=sys.stderr)

    print(f"\nResults written to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
