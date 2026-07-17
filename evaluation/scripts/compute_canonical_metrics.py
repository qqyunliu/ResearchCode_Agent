#!/usr/bin/env python3
"""Compute file-level retrieval metrics for B0 and B1 on the canonical pilot dataset.

**STATUS: legacy_debug_only**

This script was used for the Stage 2A.1 canonical baseline computation on the
old 42-record dataset. Its hardcoded default paths previously pointed to:
  - evaluation/datasets/pilot.jsonl (now overwritten with 36-record clean data)
  - evaluation/results/raw/canonical_b0_rg.jsonl (42-record CONTAMINATED raw data)
  - evaluation/results/raw/canonical_b1_keyword.jsonl (42-record CONTAMINATED raw data)

Running this script with the old defaults would now produce mismatched results
(36-record gold vs 42-record predictions). The dangerous defaults have been
removed. All paths must now be provided as command-line arguments.

Use compute_pilot_current_metrics.py for the current 36-record evaluation instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_jsonl(path: Path) -> dict[str, dict]:
    records = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                qid = rec.get("question_id")
                if qid:
                    records[qid] = rec
    return records


def get_gold_files(rec: dict) -> list[str]:
    """Get unique gold file paths from must_recall entities."""
    files = []
    seen = set()
    for e in rec.get("gold_entities", []):
        if e.get("relevance") == "must_recall":
            fp = e.get("file_path")
            if fp and fp not in seen:
                seen.add(fp)
                files.append(fp)
    return files


def get_ranked_files_b0(hits: list[dict]) -> list[str]:
    """B0 hits are already unique file paths."""
    return [h["file_path"] for h in hits]


def get_ranked_files_b1(hits: list[dict]) -> list[str]:
    """B1 hits may have multiple entities per file; deduplicate keeping first."""
    seen = set()
    files = []
    for h in hits:
        fp = h["file_path"]
        if fp not in seen:
            seen.add(fp)
            files.append(fp)
    return files


def compute_record_metrics(ranked_files: list[str], gold_files: list[str]) -> dict | None:
    """Compute Recall@k, MRR, and zero-hit for a single record."""
    gold_set = set(gold_files)
    if not gold_set:
        return None

    result = {}
    for k in (1, 5, 10):
        top_k = ranked_files[:k]
        hit = any(f in gold_set for f in top_k)
        result[f"recall@{k}"] = 1.0 if hit else 0.0

    mrr = 0.0
    for i, f in enumerate(ranked_files):
        if f in gold_set:
            mrr = 1.0 / (i + 1)
            break
    result["mrr"] = mrr

    result["zero_hit"] = 1.0 if not any(f in gold_set for f in ranked_files) else 0.0
    return result


def aggregate(records: list[dict]) -> dict:
    """Aggregate metrics over a list of record metric dicts."""
    n = len(records)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "recall@1": round(sum(m["recall@1"] for m in records) / n, 4),
        "recall@5": round(sum(m["recall@5"] for m in records) / n, 4),
        "recall@10": round(sum(m["recall@10"] for m in records) / n, 4),
        "mrr": round(sum(m["mrr"] for m in records) / n, 4),
        "zero_hit_rate": round(sum(m["zero_hit"] for m in records) / n, 4),
    }


def compute_grouped(per_record: dict, group_key: str, main_only: bool = True) -> dict:
    """Compute grouped metrics for a specific dimension."""
    groups = defaultdict(list)
    for m in per_record.values():
        if main_only and m.get("source_answerable") is not True:
            continue
        groups[m.get(group_key, "unknown")].append(m)
    result = {}
    for key in sorted(groups.keys()):
        result[key] = aggregate(groups[key])
    return result


def main() -> int:
    if len(sys.argv) < 5:
        print(
            "Usage: compute_canonical_metrics.py <dataset.jsonl> <b0.jsonl> <b1.jsonl> <output.json>",
            file=sys.stderr,
        )
        print(
            "All four arguments are required. No default paths are provided "
            "to prevent accidental use of contaminated 42-record data.",
            file=sys.stderr,
        )
        return 1

    dataset_path = Path(sys.argv[1])
    b0_path = Path(sys.argv[2])
    b1_path = Path(sys.argv[3])
    metrics_path = Path(sys.argv[4])

    with open(dataset_path, "rb") as f:
        dataset_sha = hashlib.sha256(f.read()).hexdigest()

    dataset = load_jsonl(dataset_path)
    b0_results = load_jsonl(b0_path)
    b1_results = load_jsonl(b1_path)

    print(f"Dataset SHA-256: {dataset_sha}")
    print(f"Total records: {len(dataset)}")

    # Filter eligible records
    eligible = {}
    for qid, rec in dataset.items():
        if (
            rec.get("gold_status") == "machine_verified"
            and rec.get("annotation", {}).get("review_status") == "accepted"
            and "retrieval" in rec.get("evaluation_layers", [])
        ):
            eligible[qid] = rec

    print(f"Eligible records: {len(eligible)}")

    # Compute per-record metrics
    b0_per_record = {}
    b1_per_record = {}

    for qid, rec in eligible.items():
        gold_files = get_gold_files(rec)
        if not gold_files:
            continue

        for results, get_ranked, per_record in [
            (b0_results, get_ranked_files_b0, b0_per_record),
            (b1_results, get_ranked_files_b1, b1_per_record),
        ]:
            hits = results.get(qid, {}).get("hits", [])
            ranked = get_ranked(hits)
            m = compute_record_metrics(ranked, gold_files)
            if m:
                m.update({
                    "source_answerable": rec.get("source_answerable"),
                    "system_answerable": rec.get("system_answerable"),
                    "language": rec.get("language"),
                    "difficulty": rec.get("difficulty"),
                    "task_type": rec.get("task_type"),
                })
                per_record[qid] = m

    print(f"B0 evaluated records: {len(b0_per_record)}")
    print(f"B1 evaluated records: {len(b1_per_record)}")

    # Split main vs diagnostic
    b0_main = [m for m in b0_per_record.values() if m.get("source_answerable") is True]
    b0_diag = [m for m in b0_per_record.values() if m.get("source_answerable") is False]
    b1_main = [m for m in b1_per_record.values() if m.get("source_answerable") is True]
    b1_diag = [m for m in b1_per_record.values() if m.get("source_answerable") is False]

    b0_overall = aggregate(b0_main)
    b0_diagnostic = aggregate(b0_diag)
    b1_overall = aggregate(b1_main)
    b1_diagnostic = aggregate(b1_diag)

    print(f"\nB0 overall (source_answerable=true): {b0_overall}")
    print(f"B1 overall (source_answerable=true): {b1_overall}")
    print(f"B0 diagnostic (source_answerable=false): {b0_diagnostic}")
    print(f"B1 diagnostic (source_answerable=false): {b1_diagnostic}")

    # Grouped metrics
    group_keys = ["language", "difficulty", "task_type", "system_answerable"]
    b0_grouped = {}
    b1_grouped = {}
    for gk in group_keys:
        b0_grouped[gk] = compute_grouped(b0_per_record, gk)
        b1_grouped[gk] = compute_grouped(b1_per_record, gk)

    for gk in group_keys:
        print(f"\n--- Group: {gk} ---")
        all_keys = sorted(set(list(b0_grouped[gk].keys()) + list(b1_grouped[gk].keys())))
        for key in all_keys:
            b0g = b0_grouped[gk].get(key, {"n": 0})
            b1g = b1_grouped[gk].get(key, {"n": 0})
            print(
                f"  {key}: B0(n={b0g['n']}) "
                f"R@1={b0g.get('recall@1', '-')}, "
                f"R@5={b0g.get('recall@5', '-')}, "
                f"R@10={b0g.get('recall@10', '-')}, "
                f"MRR={b0g.get('mrr', '-')}, "
                f"ZHR={b0g.get('zero_hit_rate', '-')}"
            )
            print(
                f"         B1(n={b1g['n']}) "
                f"R@1={b1g.get('recall@1', '-')}, "
                f"R@5={b1g.get('recall@5', '-')}, "
                f"R@10={b1g.get('recall@10', '-')}, "
                f"MRR={b1g.get('mrr', '-')}, "
                f"ZHR={b1g.get('zero_hit_rate', '-')}"
            )

    # Build output JSON
    output = {
        "dataset_sha256": dataset_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_records": len(dataset),
        "eligible_records": len(eligible),
        "source_answerable_true_count": len(b0_main),
        "source_answerable_false_count": len(b0_diag),
        "configuration": {
            "dataset_path": "evaluation/datasets/pilot.jsonl",
            "repo_path": "evaluation/workspaces/ruoyi-vue",
            "b0_script": "evaluation/runners/baseline_rg.py",
            "b1_script": "evaluation/runners/baseline_keyword.py",
            "top_k": 10,
            "metric_type": "file-level retrieval",
            "gold_source": "gold_entities where relevance=must_recall, field file_path",
            "eligibility_filter": (
                "gold_status=machine_verified AND review_status=accepted "
                "AND retrieval in evaluation_layers"
            ),
        },
        "b0_ripgrep": {
            "overall": b0_overall,
            "diagnostic_source_answerable_false": b0_diagnostic,
            "grouped": b0_grouped,
        },
        "b1_keyword": {
            "overall": b1_overall,
            "diagnostic_source_answerable_false": b1_diagnostic,
            "grouped": b1_grouped,
        },
    }

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nMetrics written to {metrics_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
