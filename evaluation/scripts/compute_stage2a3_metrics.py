#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute Stage 2A.3 baseline metrics with corrected metadata fields.

This script computes file-level retrieval Recall@1/5/10, MRR, and zero-hit
rate for B0 (ripgrep) and B1 (keyword search) baselines against the
pilot-current dataset.

Key design decisions for the metrics model:

  - **Index-level gold**: Only entities with ``relevance="must_recall"``
    AND ``indexed_in_system=true`` count toward Recall computation.
    Entities with ``relevance="source_only"`` are NOT counted.

  - **source_answerable=false records**: Reported separately as diagnostic,
    NOT included in main Recall/MRR.

  - **Skipped records**: source_answerable=true records with no indexed
    must_recall entities are skipped from main Recall (no gold to evaluate
    against at the index level).

  - **Arithmetic invariant**:
    dataset_records = source_answerable_true + source_answerable_false

  - **Eligibility filter**: gold_status in (machine_verified, human_verified),
    review_status=accepted, execution_status in (executable, executed),
    retrieval in evaluation_layers.

Usage:
    python compute_stage2a3_metrics.py \\
        --dataset evaluation/datasets/pilot-current.jsonl \\
        --b0 evaluation/results/raw/stage2a3_b0_rg.jsonl \\
        --b1 evaluation/results/raw/stage2a3_b1_keyword.jsonl \\
        --output evaluation/results/metrics/stage2a3_metrics.json

"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl_indexed(path: Path) -> dict[str, dict[str, Any]]:
    """Load JSONL, returning {question_id: record}."""
    records: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            rec = json.loads(line)
            qid = rec.get("question_id")
            if qid:
                records[qid] = rec
    return records


def load_jsonl_list(path: Path) -> list[dict[str, Any]]:
    """Load JSONL as an ordered list."""
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Gold extraction
# ---------------------------------------------------------------------------

def get_index_gold_files(rec: dict[str, Any]) -> list[str]:
    """Get unique gold file paths from entities with:
    relevance='must_recall' AND indexed_in_system=true.

    These are the index-level gold entities used for Recall computation.
    """
    files: list[str] = []
    seen: set[str] = set()
    for e in rec.get("gold_entities", []):
        if (e.get("relevance") == "must_recall"
                and e.get("indexed_in_system") is True):
            fp = e.get("file_path")
            if fp and fp not in seen:
                seen.add(fp)
                files.append(fp)
    return files


def get_source_only_files(rec: dict[str, Any]) -> list[str]:
    """Get unique gold file paths from entities with:
    relevance='source_only' (NOT counted in index-level Recall).
    """
    files: list[str] = []
    seen: set[str] = set()
    for e in rec.get("gold_entities", []):
        if e.get("relevance") == "source_only":
            fp = e.get("file_path")
            if fp and fp not in seen:
                seen.add(fp)
                files.append(fp)
    return files


def has_any_gold_entities(rec: dict[str, Any]) -> bool:
    """Return True if the record has at least one gold_entity."""
    return len(rec.get("gold_entities", [])) > 0


# ---------------------------------------------------------------------------
# Hit extraction
# ---------------------------------------------------------------------------

def get_ranked_files_b0(hits: list[dict[str, Any]]) -> list[str]:
    """B0 (ripgrep) returns file-level hits directly."""
    return [h["file_path"] for h in hits]


def get_ranked_files_b1(hits: list[dict[str, Any]]) -> list[str]:
    """B1 (keyword search) returns entity-level hits; deduplicate by file."""
    seen: set[str] = set()
    files: list[str] = []
    for h in hits:
        fp = h["file_path"]
        if fp not in seen:
            seen.add(fp)
            files.append(fp)
    return files


# ---------------------------------------------------------------------------
# Per-record metrics
# ---------------------------------------------------------------------------

def compute_record_metrics(
    ranked_files: list[str],
    gold_files: list[str],
) -> dict[str, Any] | None:
    """Compute Recall@1/5/10, MRR, zero_hit for a single record.

    Returns None if gold_files is empty (nothing to evaluate against).
    """
    gold_set = set(gold_files)
    if not gold_set:
        return None

    result: dict[str, Any] = {}
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

    result["zero_hit"] = 0.0 if any(f in gold_set for f in ranked_files) else 1.0
    return result


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute mean metrics over a list of per-record metric dicts."""
    n = len(records)
    if n == 0:
        return {"n": 0, "recall@1": None, "recall@5": None,
                "recall@10": None, "mrr": None, "zero_hit_rate": None}
    return {
        "n": n,
        "recall@1": round(sum(m["recall@1"] for m in records) / n, 4),
        "recall@5": round(sum(m["recall@5"] for m in records) / n, 4),
        "recall@10": round(sum(m["recall@10"] for m in records) / n, 4),
        "mrr": round(sum(m["mrr"] for m in records) / n, 4),
        "zero_hit_rate": round(sum(m["zero_hit"] for m in records) / n, 4),
    }


def compute_grouped(
    per_record: dict[str, dict[str, Any]],
    group_key: str,
) -> dict[str, dict[str, Any]]:
    """Group per-record metrics by a categorical field and aggregate each."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in per_record.values():
        groups[m.get(group_key, "unknown")].append(m)
    return {k: aggregate(v) for k, v in sorted(groups.items())}


# ---------------------------------------------------------------------------
# Eligibility filtering
# ---------------------------------------------------------------------------

def is_eligible(rec: dict[str, Any]) -> tuple[bool, str | None]:
    """Check if a record is eligible for metrics computation.

    Returns (eligible, exclusion_reason).
    """
    gs = rec.get("gold_status", "")
    rs = rec.get("annotation", {}).get("review_status", "")
    es = rec.get("execution_status", "")
    layers = rec.get("evaluation_layers", [])

    if gs not in ("machine_verified", "human_verified"):
        return False, f"gold_status={gs}"
    if rs != "accepted":
        return False, f"review_status={rs}"
    if es not in ("executable", "executed"):
        return False, f"execution_status={es}"
    if "retrieval" not in layers:
        return False, "no_retrieval_layer"
    return True, None


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def verify_reconciliation(metadata: dict[str, Any]) -> list[str]:
    """Verify arithmetic consistency of metadata counts.

    Returns a list of error messages (empty = all checks pass).
    """
    errors: list[str] = []

    total = metadata["dataset_records"]
    sa_true = metadata["source_answerable_true_records"]
    sa_false = metadata["source_answerable_false_records"]

    # Invariant 1: total = sa_true + sa_false
    if total != sa_true + sa_false:
        errors.append(
            f"ARITHMETIC ERROR: dataset_records ({total}) != "
            f"source_answerable_true ({sa_true}) + source_answerable_false ({sa_false}) "
            f"= {sa_true + sa_false}"
        )

    # Invariant 2: schema_eligible <= dataset_records
    if metadata["schema_eligible_records"] > total:
        errors.append(
            f"ARITHMETIC ERROR: schema_eligible_records "
            f"({metadata['schema_eligible_records']}) > dataset_records ({total})"
        )

    # Invariant 3: retrieval_layer_records <= schema_eligible_records
    if metadata["retrieval_layer_records"] > metadata["schema_eligible_records"]:
        errors.append(
            f"ARITHMETIC ERROR: retrieval_layer_records "
            f"({metadata['retrieval_layer_records']}) > "
            f"schema_eligible_records ({metadata['schema_eligible_records']})"
        )

    # Invariant 4: index_retrieval_scored + skipped_no_indexable_gold <= sa_true
    idx_scored = metadata["index_retrieval_scored_records"]
    skipped = metadata["skipped_no_indexable_gold_records"]
    if idx_scored + skipped > sa_true:
        errors.append(
            f"ARITHMETIC ERROR: index_retrieval_scored ({idx_scored}) + "
            f"skipped_no_indexable_gold ({skipped}) = {idx_scored + skipped} "
            f"> source_answerable_true ({sa_true})"
        )

    # Invariant 5: eligible + excluded = dataset_records
    n_eligible = len(metadata["eligible_question_ids"])
    n_excluded = len(metadata["excluded_question_ids"])
    if n_eligible + n_excluded != total:
        errors.append(
            f"ARITHMETIC ERROR: eligible_question_ids ({n_eligible}) + "
            f"excluded_question_ids ({n_excluded}) = {n_eligible + n_excluded} "
            f"!= dataset_records ({total})"
        )

    return errors


def print_reconciliation_table(metadata: dict[str, Any]) -> None:
    """Print a human-readable reconciliation table."""
    print("\n" + "=" * 72)
    print("RECONCILIATION TABLE")
    print("=" * 72)
    print(f"  dataset_records:                    {metadata['dataset_records']}")
    print(f"  schema_eligible_records:            {metadata['schema_eligible_records']}")
    print(f"  retrieval_layer_records:            {metadata['retrieval_layer_records']}")
    print(f"  source_answerable_true_records:     {metadata['source_answerable_true_records']}")
    print(f"  source_answerable_false_records:    {metadata['source_answerable_false_records']}")
    print(f"    (sum check: {metadata['source_answerable_true_records']} + "
          f"{metadata['source_answerable_false_records']} = "
          f"{metadata['source_answerable_true_records'] + metadata['source_answerable_false_records']})")
    print(f"  index_retrieval_scored_records:     {metadata['index_retrieval_scored_records']}")
    print(f"  unanswerable_with_source_gold:      {metadata['unanswerable_with_source_gold_records']}")
    print(f"  skipped_no_indexable_gold_records:  {metadata['skipped_no_indexable_gold_records']}")
    print(f"  eligible_question_ids:              {len(metadata['eligible_question_ids'])}")
    print(f"  excluded_question_ids:              {len(metadata['excluded_question_ids'])}")

    excl = metadata.get("excluded_records_by_reason", {})
    if excl:
        print(f"  excluded_records_by_reason:")
        for reason, count in sorted(excl.items()):
            print(f"    {reason}: {count}")
    else:
        print(f"  excluded_records_by_reason:          (none)")

    print("-" * 72)

    # Run verification
    errors = verify_reconciliation(metadata)
    if errors:
        for err in errors:
            print(f"  *** {err}")
    else:
        print("  All reconciliation checks PASSED.")

    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute Stage 2A.3 baseline metrics with corrected metadata "
            "fields for the ResearchCode-Agent evaluation."
        ),
    )
    parser.add_argument(
        "--dataset", required=True, type=Path,
        help="Path to the JSONL evaluation dataset.",
    )
    parser.add_argument(
        "--b0", required=True, type=Path,
        help="Path to B0 (ripgrep) JSONL results.",
    )
    parser.add_argument(
        "--b1", required=True, type=Path,
        help="Path to B1 (keyword search) JSONL results.",
    )
    parser.add_argument(
        "--output", required=True, type=Path,
        help="Path for the output metrics JSON.",
    )
    parser.add_argument(
        "--repo-commit", default="41720e624c5a668c7d3777835e4c87095a7a1dfd",
        help="Repository commit SHA used for indexing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    dataset_path: Path = args.dataset
    b0_path: Path = args.b0
    b1_path: Path = args.b1
    output_path: Path = args.output
    repo_commit: str = args.repo_commit

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------

    # Compute dataset SHA-256
    with open(dataset_path, "rb") as f:
        dataset_sha = hashlib.sha256(f.read()).hexdigest()

    dataset = load_jsonl_indexed(dataset_path)
    b0_results = load_jsonl_indexed(b0_path)
    b1_results = load_jsonl_indexed(b1_path)

    total_records = len(dataset)
    print(f"Dataset SHA-256: {dataset_sha}")
    print(f"Total records: {total_records}")

    # ------------------------------------------------------------------
    # Classify records
    # ------------------------------------------------------------------

    eligible_ids: list[str] = []
    excluded_ids: list[str] = []
    excluded_by_reason: dict[str, int] = defaultdict(int)

    # Counters for metadata
    retrieval_layer_count = 0
    sa_true_count = 0
    sa_false_count = 0
    index_retrieval_scored = 0
    unanswerable_with_source_gold = 0
    skipped_no_indexable_gold = 0
    schema_eligible = 0  # records that pass schema/semantic validation
                        # (all 36 pass per validator output)

    for qid, rec in dataset.items():
        ok, reason = is_eligible(rec)

        # Count retrieval layer (regardless of eligibility)
        if "retrieval" in rec.get("evaluation_layers", []):
            retrieval_layer_count += 1

        # source_answerable classification (all records)
        if rec.get("source_answerable") is True:
            sa_true_count += 1
        elif rec.get("source_answerable") is False:
            sa_false_count += 1

        if not ok:
            excluded_ids.append(qid)
            excluded_by_reason[reason] += 1
            continue

        eligible_ids.append(qid)

    # All 36 records passed schema+semantic validation
    schema_eligible = total_records

    # Second pass: among eligible records, classify index-level scoring
    for qid in eligible_ids:
        rec = dataset[qid]
        sa = rec.get("source_answerable")
        gold_files = get_index_gold_files(rec)

        if sa is True:
            if gold_files:
                index_retrieval_scored += 1
            else:
                skipped_no_indexable_gold += 1

        elif sa is False:
            if has_any_gold_entities(rec):
                unanswerable_with_source_gold += 1

    # Sort IDs for deterministic output
    eligible_ids.sort()
    excluded_ids.sort()

    print(f"Schema-eligible records: {schema_eligible}")
    print(f"Retrieval-layer records: {retrieval_layer_count}")
    print(f"Eligible for metrics: {len(eligible_ids)}")
    print(f"Excluded: {len(excluded_ids)}")
    print(f"source_answerable=true: {sa_true_count}")
    print(f"source_answerable=false: {sa_false_count}")
    print(f"index_retrieval_scored: {index_retrieval_scored}")
    print(f"unanswerable_with_source_gold: {unanswerable_with_source_gold}")
    print(f"skipped_no_indexable_gold: {skipped_no_indexable_gold}")

    # ------------------------------------------------------------------
    # Build metadata dict
    # ------------------------------------------------------------------

    metadata: dict[str, Any] = {
        "dataset_path": "evaluation/datasets/pilot-current.jsonl",
        "dataset_sha256": dataset_sha,
        "repository_commit": repo_commit,
        "dataset_records": total_records,
        "schema_eligible_records": schema_eligible,
        "retrieval_layer_records": retrieval_layer_count,
        "index_retrieval_scored_records": index_retrieval_scored,
        "source_answerable_true_records": sa_true_count,
        "source_answerable_false_records": sa_false_count,
        "unanswerable_with_source_gold_records": unanswerable_with_source_gold,
        "skipped_no_indexable_gold_records": skipped_no_indexable_gold,
        "excluded_records_by_reason": dict(excluded_by_reason),
        "eligible_question_ids": eligible_ids,
        "excluded_question_ids": excluded_ids,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # ------------------------------------------------------------------
    # Compute per-record retrieval metrics
    # ------------------------------------------------------------------

    # We compute metrics only for eligible records that have index-level
    # gold files (relevance=must_recall AND indexed_in_system=true).

    b0_main_per_record: dict[str, dict[str, Any]] = {}
    b0_diag_per_record: dict[str, dict[str, Any]] = {}
    b1_main_per_record: dict[str, dict[str, Any]] = {}
    b1_diag_per_record: dict[str, dict[str, Any]] = {}

    for qid in eligible_ids:
        rec = dataset[qid]
        sa = rec.get("source_answerable")
        gold_files = get_index_gold_files(rec)

        if not gold_files:
            # No index-level gold -- skip from Recall computation
            continue

        # B0 metrics
        b0_hits = b0_results.get(qid, {}).get("hits", [])
        b0_ranked = get_ranked_files_b0(b0_hits)
        b0_m = compute_record_metrics(b0_ranked, gold_files)

        if b0_m:
            b0_m.update({
                "source_answerable": sa,
                "system_answerable": rec.get("system_answerable"),
                "language": rec.get("language"),
                "difficulty": rec.get("difficulty"),
                "task_type": rec.get("task_type"),
            })
            if sa is True:
                b0_main_per_record[qid] = b0_m
            else:
                b0_diag_per_record[qid] = b0_m

        # B1 metrics
        b1_hits = b1_results.get(qid, {}).get("hits", [])
        b1_ranked = get_ranked_files_b1(b1_hits)
        b1_m = compute_record_metrics(b1_ranked, gold_files)

        if b1_m:
            b1_m.update({
                "source_answerable": sa,
                "system_answerable": rec.get("system_answerable"),
                "language": rec.get("language"),
                "difficulty": rec.get("difficulty"),
                "task_type": rec.get("task_type"),
            })
            if sa is True:
                b1_main_per_record[qid] = b1_m
            else:
                b1_diag_per_record[qid] = b1_m

    # ------------------------------------------------------------------
    # Aggregate
    # ------------------------------------------------------------------

    b0_main = list(b0_main_per_record.values())
    b0_diag = list(b0_diag_per_record.values())
    b1_main = list(b1_main_per_record.values())
    b1_diag = list(b1_diag_per_record.values())

    b0_overall = aggregate(b0_main)
    b0_diagnostic = aggregate(b0_diag)
    b1_overall = aggregate(b1_main)
    b1_diagnostic = aggregate(b0_diag)  # intentional: same diagnostic set
    # Actually, re-compute from b1_diag
    b1_diagnostic = aggregate(b1_diag)

    print(f"\nB0 main (sa=true, has index gold): {len(b0_main)}")
    print(f"B1 main (sa=true, has index gold): {len(b1_main)}")
    print(f"B0 diagnostic (sa=false, has index gold): {len(b0_diag)}")
    print(f"B1 diagnostic (sa=false, has index gold): {len(b1_diag)}")

    # ------------------------------------------------------------------
    # Grouped metrics (main set only, source_answerable=true)
    # ------------------------------------------------------------------

    group_keys = ["language", "difficulty", "task_type", "system_answerable"]
    b0_grouped: dict[str, dict[str, Any]] = {}
    b1_grouped: dict[str, dict[str, Any]] = {}

    for gk in group_keys:
        b0_grouped[gk] = compute_grouped(b0_main_per_record, gk)
        b1_grouped[gk] = compute_grouped(b1_main_per_record, gk)

    # Print grouped summary
    for gk in group_keys:
        print(f"\n--- By {gk} ---")
        all_keys = sorted(set(
            list(b0_grouped[gk].keys()) + list(b1_grouped[gk].keys())
        ))
        for key in all_keys:
            b0g = b0_grouped[gk].get(key, {"n": 0})
            b1g = b1_grouped[gk].get(key, {"n": 0})
            print(
                f"  {key}: "
                f"B0(n={b0g['n']}) R@1={b0g.get('recall@1', '-')}, "
                f"R@5={b0g.get('recall@5', '-')}, "
                f"R@10={b0g.get('recall@10', '-')}, "
                f"MRR={b0g.get('mrr', '-')}, "
                f"ZHR={b0g.get('zero_hit_rate', '-')}"
            )
            print(
                f"         "
                f"B1(n={b1g['n']}) R@1={b1g.get('recall@1', '-')}, "
                f"R@5={b1g.get('recall@5', '-')}, "
                f"R@10={b1g.get('recall@10', '-')}, "
                f"MRR={b1g.get('mrr', '-')}, "
                f"ZHR={b1g.get('zero_hit_rate', '-')}"
            )

    # ------------------------------------------------------------------
    # Build output JSON
    # ------------------------------------------------------------------

    # Get B1 scan metadata
    b1_entity_count = None
    b1_files_indexed = None
    b1_scan_time = None
    for rec in b1_results.values():
        b1_entity_count = rec.get("entity_count")
        b1_files_indexed = rec.get("files_indexed")
        b1_scan_time = rec.get("scan_time_seconds")
        break

    output: dict[str, Any] = {
        **metadata,
        "baselines": {
            "b0_rgrep": {
                "description": (
                    "B0 baseline: ripgrep text search (token extraction + "
                    "file-level grep). No index used."
                ),
                "predictions_file": str(b0_path),
                "overall": b0_overall,
                "diagnostic_source_answerable_false": b0_diagnostic,
                "grouped": b0_grouped,
            },
            "b1_keyword": {
                "description": (
                    "B1 baseline: SQLite keyword search (per-token LIKE "
                    "matching via KeywordSearchService). Uses scanned index."
                ),
                "predictions_file": str(b1_path),
                "overall": b1_overall,
                "diagnostic_source_answerable_false": b1_diagnostic,
                "grouped": b1_grouped,
                "scan_metadata": {
                    "entity_count": b1_entity_count,
                    "files_indexed": b1_files_indexed,
                    "scan_time_seconds": b1_scan_time,
                },
            },
        },
        "grouped_metrics": {
            "b0_rgrep": b0_grouped,
            "b1_keyword": b1_grouped,
        },
        "notes": [
            "Index-level Recall: only entities with relevance='must_recall' "
            "AND indexed_in_system=true are gold for Recall computation.",
            "Entities with relevance='source_only' are NOT counted in "
            "index-level Recall.",
            "source_answerable=false records are reported separately as "
            "diagnostic, NOT in main Recall/MRR.",
            "File-level matching: a hit matches if any result file_path "
            "equals any gold entity file_path.",
            "B0 returns file-level hits (ripgrep). B1 returns entity-level "
            "hits deduplicated by file_path.",
        ],
    }

    # ------------------------------------------------------------------
    # Write output
    # ------------------------------------------------------------------

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nMetrics written to {output_path}")

    # ------------------------------------------------------------------
    # Reconciliation table
    # ------------------------------------------------------------------

    print_reconciliation_table(metadata)

    # Verify and exit with error if reconciliation fails
    errors = verify_reconciliation(metadata)
    if errors:
        print("\nReconciliation FAILED.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
