#!/usr/bin/env python3
"""Compute file-level retrieval metrics for B0 and B1 on the pilot-current dataset.

Reads from:
  - evaluation/datasets/pilot-current.jsonl
  - evaluation/results/raw/pilot_current_b0_rg.jsonl
  - evaluation/results/raw/pilot_current_b1_keyword.jsonl

Writes to:
  - evaluation/results/metrics/pilot_current_metrics.json
  - evaluation/results/metrics/pilot_current_summary.md

Eligibility filter:
  gold_status=machine_verified AND review_status=accepted
  AND execution_status in (executable, executed)
  AND retrieval in evaluation_layers

Gold files: from gold_entities where relevance=must_recall, field file_path.
"""

from __future__ import annotations

import hashlib
import json
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
    return [h["file_path"] for h in hits]


def get_ranked_files_b1(hits: list[dict]) -> list[str]:
    seen = set()
    files = []
    for h in hits:
        fp = h["file_path"]
        if fp not in seen:
            seen.add(fp)
            files.append(fp)
    return files


def compute_record_metrics(ranked_files: list[str], gold_files: list[str]) -> dict | None:
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


def compute_grouped(per_record: dict, group_key: str) -> dict:
    groups = defaultdict(list)
    for m in per_record.values():
        if m.get("source_answerable") is not True:
            continue
        groups[m.get(group_key, "unknown")].append(m)
    result = {}
    for key in sorted(groups.keys()):
        result[key] = aggregate(groups[key])
    return result


def fmt_metric(val):
    if val is None:
        return "-"
    return f"{val:.4f}" if isinstance(val, float) else str(val)


def write_summary_md(
    output_path: Path,
    dataset_sha: str,
    total: int,
    eligible: int,
    excluded_reasons: dict[str, int],
    b0_overall: dict,
    b1_overall: dict,
    b0_grouped: dict,
    b1_grouped: dict,
    b0_diag: dict,
    b1_diag: dict,
    b0_main_count: int,
    b1_main_count: int,
    b0_diag_count: int,
    b1_diag_count: int,
    no_gold_count: int,
    b0_entity_count: int | None,
):
    lines = []
    lines.append("# Pilot-Current Baseline Retrieval Metrics")
    lines.append("")
    lines.append("## Dataset")
    lines.append("")
    lines.append(f"- **Dataset**: `evaluation/datasets/pilot-current.jsonl`")
    lines.append(f"- **SHA-256**: `{dataset_sha}`")
    lines.append(f"- **Total records**: {total}")
    lines.append(f"- **Eligible records** (machine_verified + accepted + executable + retrieval layer): {eligible}")
    lines.append(f"- **Records with gold files** (must_recall entities with file_path):")
    lines.append(f"  - source_answerable=true: {b0_main_count}")
    lines.append(f"  - source_answerable=false (diagnostic): {b0_diag_count}")
    lines.append(f"- **Records without gold files** (skipped from recall): {no_gold_count}")
    if excluded_reasons:
        lines.append(f"- **Excluded records**: {sum(excluded_reasons.values())}")
        for reason, count in sorted(excluded_reasons.items()):
            lines.append(f"  - {reason}: {count}")
    lines.append("")

    lines.append("## Overall Metrics (source_answerable=true)")
    lines.append("")
    lines.append(f"| Metric | B0 (ripgrep, n={b0_overall.get('n', 0)}) | B1 (keyword, n={b1_overall.get('n', 0)}) |")
    lines.append("|---|---|---|")
    for metric in ["recall@1", "recall@5", "recall@10", "mrr", "zero_hit_rate"]:
        label = metric.replace("_", " ").title().replace("@", "@")
        b0v = fmt_metric(b0_overall.get(metric))
        b1v = fmt_metric(b1_overall.get(metric))
        lines.append(f"| {label} | {b0v} | {b1v} |")
    lines.append("")

    lines.append("## Diagnostic Metrics (source_answerable=false)")
    lines.append("")
    lines.append(f"| Metric | B0 (ripgrep, n={b0_diag.get('n', 0)}) | B1 (keyword, n={b1_diag.get('n', 0)}) |")
    lines.append("|---|---|---|")
    for metric in ["recall@1", "recall@5", "recall@10", "mrr", "zero_hit_rate"]:
        label = metric.replace("_", " ").title().replace("@", "@")
        b0v = fmt_metric(b0_diag.get(metric))
        b1v = fmt_metric(b1_diag.get(metric))
        lines.append(f"| {label} | {b0v} | {b1v} |")
    lines.append("")

    lines.append("## Grouped Metrics (source_answerable=true only)")
    lines.append("")

    for group_key, group_label in [
        ("language", "Language"),
        ("difficulty", "Difficulty"),
        ("task_type", "Task Type"),
    ]:
        lines.append(f"### By {group_label}")
        lines.append("")

        b0g = b0_grouped.get(group_key, {})
        b1g = b1_grouped.get(group_key, {})
        all_keys = sorted(set(list(b0g.keys()) + list(b1g.keys())))

        for key in all_keys:
            b0m = b0g.get(key, {"n": 0})
            b1m = b1g.get(key, {"n": 0})
            lines.append(f"**{key}** (B0 n={b0m['n']}, B1 n={b1m['n']})")
            lines.append("")
            lines.append("| Metric | B0 | B1 |")
            lines.append("|---|---|---|")
            for metric in ["recall@1", "recall@5", "recall@10", "mrr", "zero_hit_rate"]:
                label = metric.replace("_", " ").title().replace("@", "@")
                lines.append(f"| {label} | {fmt_metric(b0m.get(metric))} | {fmt_metric(b1m.get(metric))} |")
            lines.append("")

    lines.append("## Comparison with Old Contaminated Baseline (pilot.jsonl)")
    lines.append("")
    lines.append("The old `pilot.jsonl` dataset (42 records) was found to contain data contamination")
    lines.append("from proposed annotations. This `pilot-current.jsonl` (36 records) is the clean")
    lines.append("version with only verified gold data.")
    lines.append("")
    lines.append("Key differences:")
    lines.append(f"- Record count: 36 (current) vs 42 (old)")
    lines.append(f"- All 36 current records have execution_status='executable'")
    lines.append(f"- Language split: 18 zh / 18 en (balanced), vs the old dataset's imbalance")
    lines.append(f"- Task types: 12 CODE_QA / 12 TRACE_CHAIN / 12 CHANGE_PLAN (balanced)")
    lines.append("")
    if b0_entity_count is not None:
        lines.append(f"## Configuration")
        lines.append("")
        lines.append(f"- B1 scan: {b0_entity_count} entities indexed from the repository")
        lines.append(f"- Top-k: 10")
        lines.append(f"- Metrics script: `evaluation/scripts/compute_pilot_current_metrics.py`")
        lines.append(f"- Full metrics JSON: `evaluation/results/metrics/pilot_current_metrics.json`")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    base = Path(__file__).resolve().parent.parent
    dataset_path = base / "datasets" / "pilot-current.jsonl"
    b0_path = base / "results" / "raw" / "pilot_current_b0_rg.jsonl"
    b1_path = base / "results" / "raw" / "pilot_current_b1_keyword.jsonl"
    metrics_path = base / "results" / "metrics" / "pilot_current_metrics.json"
    summary_path = base / "results" / "metrics" / "pilot_current_summary.md"

    # SHA-256
    with open(dataset_path, "rb") as f:
        dataset_sha = hashlib.sha256(f.read()).hexdigest()

    dataset = load_jsonl(dataset_path)
    b0_results = load_jsonl(b0_path)
    b1_results = load_jsonl(b1_path)

    print(f"Dataset SHA-256: {dataset_sha}")
    print(f"Total records: {len(dataset)}")

    # Filter eligible records
    eligible = {}
    excluded_reasons: dict[str, int] = defaultdict(int)

    for qid, rec in dataset.items():
        gs = rec.get("gold_status", "")
        rs = rec.get("annotation", {}).get("review_status", "")
        es = rec.get("execution_status", "")
        layers = rec.get("evaluation_layers", [])

        if gs != "machine_verified":
            excluded_reasons[f"gold_status={gs}"] += 1
            continue
        if rs != "accepted":
            excluded_reasons[f"review_status={rs}"] += 1
            continue
        if es not in ("executable", "executed"):
            excluded_reasons[f"execution_status={es}"] += 1
            continue
        if "retrieval" not in layers:
            excluded_reasons["no retrieval layer"] += 1
            continue
        eligible[qid] = rec

    print(f"Eligible records: {len(eligible)}")
    print(f"Excluded reasons: {dict(excluded_reasons)}")

    # Compute per-record metrics
    b0_per_record = {}
    b1_per_record = {}
    no_gold_count = 0

    for qid, rec in eligible.items():
        gold_files = get_gold_files(rec)
        if not gold_files:
            no_gold_count += 1
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

    # Split main vs diagnostic
    b0_main = [m for m in b0_per_record.values() if m.get("source_answerable") is True]
    b0_diag = [m for m in b0_per_record.values() if m.get("source_answerable") is False]
    b1_main = [m for m in b1_per_record.values() if m.get("source_answerable") is True]
    b1_diag = [m for m in b1_per_record.values() if m.get("source_answerable") is False]

    b0_overall = aggregate(b0_main)
    b0_diagnostic = aggregate(b0_diag)
    b1_overall = aggregate(b1_main)
    b1_diagnostic = aggregate(b1_diag)

    print(f"B0 evaluated (source_answerable=true): {len(b0_main)}")
    print(f"B1 evaluated (source_answerable=true): {len(b1_main)}")
    print(f"B0 diagnostic (source_answerable=false): {len(b0_diag)}")
    print(f"B1 diagnostic (source_answerable=false): {len(b1_diag)}")
    print(f"No gold files: {no_gold_count}")

    # Grouped metrics
    group_keys = ["language", "difficulty", "task_type"]
    b0_grouped = {}
    b1_grouped = {}
    for gk in group_keys:
        b0_grouped[gk] = compute_grouped(b0_per_record, gk)
        b1_grouped[gk] = compute_grouped(b1_per_record, gk)

    for gk in group_keys:
        print(f"\n--- {gk} ---")
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

    # Get B1 entity count
    b1_entity_count = None
    for rec in b1_results.values():
        b1_entity_count = rec.get("entity_count")
        break

    # Build output JSON
    output = {
        "dataset_sha256": dataset_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_path": "evaluation/datasets/pilot-current.jsonl",
        "total_records": len(dataset),
        "eligible_records": len(eligible),
        "excluded_reasons": dict(excluded_reasons),
        "no_gold_files_count": no_gold_count,
        "source_answerable_true_count": len(b0_main),
        "source_answerable_false_count": len(b0_diag),
        "configuration": {
            "dataset_path": "evaluation/datasets/pilot-current.jsonl",
            "repo_path": "evaluation/workspaces/ruoyi-vue",
            "b0_script": "evaluation/runners/baseline_rg.py",
            "b1_script": "evaluation/runners/baseline_keyword.py",
            "top_k": 10,
            "metric_type": "file-level retrieval",
            "gold_source": "gold_entities where relevance=must_recall, field file_path",
            "eligibility_filter": (
                "gold_status=machine_verified AND review_status=accepted "
                "AND execution_status in (executable, executed) "
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
            "entity_count": b1_entity_count,
        },
    }

    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nMetrics written to {metrics_path}")

    # Write summary MD
    write_summary_md(
        summary_path,
        dataset_sha=dataset_sha,
        total=len(dataset),
        eligible=len(eligible),
        excluded_reasons=dict(excluded_reasons),
        b0_overall=b0_overall,
        b1_overall=b1_overall,
        b0_grouped=b0_grouped,
        b1_grouped=b1_grouped,
        b0_diag=b0_diagnostic,
        b1_diag=b1_diagnostic,
        b0_main_count=len(b0_main),
        b1_main_count=len(b1_main),
        b0_diag_count=len(b0_diag),
        b1_diag_count=len(b1_diag),
        no_gold_count=no_gold_count,
        b0_entity_count=b1_entity_count,
    )
    print(f"Summary written to {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
