#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a Markdown evaluation report from metrics JSON and dataset JSONL.

Reads:
  - A metrics JSON file (produced by compute_baseline_metrics or similar).
  - A dataset JSONL file for cross-distribution tables.

Writes:
  - A Markdown report to the specified output path.

CLI:
  python generate_report.py --metrics METRICS_JSON --dataset DATASET_JSON --output OUTPUT_MD

The script refuses to generate if the dataset file's SHA-256 does not match
the ``dataset_sha256`` recorded in the metrics JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# =====================================================================
# Helpers
# =====================================================================


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt(value: Any, decimals: int = 4) -> str:
    """Format a numeric value to a fixed number of decimal places."""
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def _load_jsonl(path: Path) -> list[dict]:
    """Load all records from a JSONL file."""
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def _normalize_metrics(metrics: dict) -> dict:
    """Return one report-facing shape for legacy and Stage 2A.3 metrics.

    Stage 2A.3 made the evaluation scopes explicit and nested baseline results
    under ``baselines``.  Keeping the translation here lets old archived
    metrics remain readable without making the report silently print ``N/A``.
    """
    if "dataset_records" not in metrics:
        return metrics

    normalized = dict(metrics)
    normalized["total_records"] = metrics["dataset_records"]
    normalized["eligible_records"] = metrics["schema_eligible_records"]
    normalized["source_answerable_true_count"] = metrics[
        "source_answerable_true_records"
    ]
    normalized["source_answerable_false_count"] = metrics[
        "source_answerable_false_records"
    ]
    # In the Stage 2A.3 model, no-indexable-gold is a subset/diagnostic, not a
    # third answerability bucket.  It must not be added during reconciliation.
    normalized["no_gold_files_count"] = 0
    normalized["skipped_no_indexable_gold_records"] = metrics.get(
        "skipped_no_indexable_gold_records", 0
    )
    normalized["excluded_reasons"] = metrics.get(
        "excluded_records_by_reason", {}
    )
    normalized.update(metrics.get("baselines", {}))
    return normalized


def _build_cross_table(
    records: list[dict],
    row_key: str,
    col_key: str,
) -> list[list[str]]:
    """Build a cross-distribution count table.

    Returns a list of rows suitable for a Markdown table.
    The first row is the header.
    """
    counter: Counter[tuple[str, str]] = Counter()
    row_vals: set[str] = set()
    col_vals: set[str] = set()

    for rec in records:
        rv = str(rec.get(row_key, "unknown"))
        cv = str(rec.get(col_key, "unknown"))
        counter[(rv, cv)] += 1
        row_vals.add(rv)
        col_vals.add(cv)

    sorted_rows = sorted(row_vals)
    sorted_cols = sorted(col_vals)

    # Header
    header = f"| {row_key} \\ {col_key} | " + " | ".join(sorted_cols) + " | total |"
    sep = "|---|" + "|".join(["---"] * len(sorted_cols)) + "|---|"

    rows = [header, sep]
    for rv in sorted_rows:
        cells = []
        row_total = 0
        for cv in sorted_cols:
            cnt = counter.get((rv, cv), 0)
            cells.append(str(cnt))
            row_total += cnt
        cells.append(str(row_total))
        rows.append(f"| {rv} | " + " | ".join(cells) + " |")

    # Column totals row
    col_totals = []
    grand = 0
    for cv in sorted_cols:
        t = sum(counter.get((rv, cv), 0) for rv in sorted_rows)
        col_totals.append(str(t))
        grand += t
    col_totals.append(str(grand))
    rows.append(f"| **total** | " + " | ".join(col_totals) + " |")

    return rows


# =====================================================================
# Section generators
# =====================================================================


def _section_a(metrics: dict, dataset_records: list[dict], dataset_path: Path) -> list[str]:
    """Section A: Dataset Summary."""
    lines: list[str] = []
    lines.append("# Section A: Dataset Summary")
    lines.append("")

    ds_sha = metrics.get("dataset_sha256", "N/A")
    ds_path = metrics.get("dataset_path", str(dataset_path))
    config = metrics.get("configuration", {})
    commit_sha = "N/A"
    # Try to extract commit from the first dataset record
    if dataset_records:
        commit_sha = dataset_records[0].get("commit_sha", "N/A")

    lines.append("## Dataset Identity")
    lines.append("")
    lines.append(f"- **Dataset path**: `{ds_path}`")
    lines.append(f"- **SHA-256**: `{ds_sha}`")
    lines.append(f"- **Repository commit**: `{commit_sha}`")
    lines.append("")

    # Record counts
    lines.append("## Record Counts")
    lines.append("")
    lines.append(f"- **Total records**: {metrics.get('total_records', 'N/A')}")
    lines.append(f"- **Eligible records**: {metrics.get('eligible_records', 'N/A')}")
    lines.append(f"- **source_answerable=true**: {metrics.get('source_answerable_true_count', 'N/A')}")
    lines.append(f"- **source_answerable=false**: {metrics.get('source_answerable_false_count', 'N/A')}")
    lines.append(f"- **No gold files**: {metrics.get('no_gold_files_count', 'N/A')}")
    if "skipped_no_indexable_gold_records" in metrics:
        lines.append(
            "- **Skipped: no indexable gold**: "
            f"{metrics['skipped_no_indexable_gold_records']}"
        )

    # Excluded reasons
    excluded = metrics.get("excluded_reasons", {})
    if excluded:
        lines.append("")
        lines.append("### Excluded Reasons")
        lines.append("")
        for reason, count in sorted(excluded.items()):
            lines.append(f"- {reason}: {count}")

    lines.append("")

    # Cross-distribution tables
    lines.append("## Cross-Distribution Tables")
    lines.append("")

    # Task Type x Language
    lines.append("### Task Type x Language")
    lines.append("")
    for row in _build_cross_table(dataset_records, "task_type", "language"):
        lines.append(row)
    lines.append("")

    # Task Type x Difficulty
    lines.append("### Task Type x Difficulty")
    lines.append("")
    for row in _build_cross_table(dataset_records, "task_type", "difficulty"):
        lines.append(row)
    lines.append("")

    # Task Type x system_answerable
    lines.append("### Task Type x system_answerable")
    lines.append("")
    for row in _build_cross_table(dataset_records, "task_type", "system_answerable"):
        lines.append(row)
    lines.append("")

    return lines


def _baseline_overall_table(baseline: dict) -> list[str]:
    """Build the overall metrics table for a single baseline."""
    overall = baseline.get("overall", {})
    metric_keys = ["recall@1", "recall@5", "recall@10", "mrr", "zero_hit_rate"]
    lines: list[str] = []
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for mk in metric_keys:
        lines.append(f"| {mk} | {_fmt(overall.get(mk))} |")
    return lines


def _grouped_table(baseline: dict, group_name: str) -> list[str]:
    """Build a grouped metrics table for a single baseline and group."""
    grouped = baseline.get("grouped", {})
    group_data = grouped.get(group_name, {})
    if not group_data:
        return [f"*No {group_name} groups found.*"]

    metric_keys = ["recall@1", "recall@5", "recall@10", "mrr", "zero_hit_rate"]

    lines: list[str] = []
    lines.append(f"| {group_name} | n | " + " | ".join(metric_keys) + " |")
    lines.append("|---|---|" + "|".join(["---"] * len(metric_keys)) + "|")

    for group_val in sorted(group_data.keys()):
        gd = group_data[group_val]
        n = gd.get("n", "N/A")
        cells = [_fmt(gd.get(mk)) for mk in metric_keys]
        lines.append(f"| {group_val} | {n} | " + " | ".join(cells) + " |")

    return lines


def _section_b(metrics: dict) -> list[str]:
    """Section B: Baseline Results."""
    lines: list[str] = []
    lines.append("# Section B: Baseline Results")
    lines.append("")

    # Identify baseline keys (b0 and b1)
    b0_key = None
    b1_key = None
    for k in metrics:
        if k.startswith("b0"):
            b0_key = k
        elif k.startswith("b1"):
            b1_key = k

    baselines: list[tuple[str, str, dict]] = []
    if b0_key:
        baselines.append(("B0", b0_key, metrics[b0_key]))
    if b1_key:
        baselines.append(("B1", b1_key, metrics[b1_key]))

    # Overall comparison table
    lines.append("## Overall Metrics")
    lines.append("")

    if baselines:
        metric_keys = ["recall@1", "recall@5", "recall@10", "mrr", "zero_hit_rate"]

        # Build header with all baselines
        header = "| Metric | " + " | ".join(
            f"{label} ({raw_key}, n={bl.get('overall', {}).get('n', '?')})"
            for label, raw_key, bl in baselines
        ) + " |"
        sep = "|---|" + "|".join(["---"] * len(baselines)) + "|"
        lines.append(header)
        lines.append(sep)

        for mk in metric_keys:
            cells = []
            for _, _, bl in baselines:
                overall = bl.get("overall", {})
                cells.append(_fmt(overall.get(mk)))
            lines.append(f"| {mk} | " + " | ".join(cells) + " |")
    lines.append("")

    # Diagnostic (source_answerable=false)
    lines.append("## Diagnostic: source_answerable=false")
    lines.append("")
    if baselines:
        header = "| Metric | " + " | ".join(
            f"{label} (n={bl.get('diagnostic_source_answerable_false', {}).get('n', '?')})"
            for label, _, bl in baselines
        ) + " |"
        sep = "|---|" + "|".join(["---"] * len(baselines)) + "|"
        lines.append(header)
        lines.append(sep)

        metric_keys = ["recall@1", "recall@5", "recall@10", "mrr", "zero_hit_rate"]
        for mk in metric_keys:
            cells = []
            for _, _, bl in baselines:
                diag = bl.get("diagnostic_source_answerable_false", {})
                cells.append(_fmt(diag.get(mk)))
            lines.append(f"| {mk} | " + " | ".join(cells) + " |")
    lines.append("")

    # Grouped metrics for each baseline
    group_names = ["language", "difficulty", "task_type"]
    for group_name in group_names:
        lines.append(f"## Grouped by {group_name}")
        lines.append("")

        for label, raw_key, bl in baselines:
            lines.append(f"### {label} ({raw_key})")
            lines.append("")
            for row in _grouped_table(bl, group_name):
                lines.append(row)
            lines.append("")

    return lines


def _section_c(metrics: dict) -> list[str]:
    """Section C: Consistency Checks."""
    lines: list[str] = []
    lines.append("# Section C: Consistency Checks")
    lines.append("")

    total = metrics.get("total_records", 0)
    eligible = metrics.get("eligible_records", 0)
    true_count = metrics.get("source_answerable_true_count", 0)
    false_count = metrics.get("source_answerable_false_count", 0)
    no_gold = metrics.get("no_gold_files_count", 0)

    # Check 1: total_records = true + false + no_gold_files
    sum_parts = true_count + false_count + no_gold
    check1_ok = total == sum_parts
    lines.append("## Record Count Reconciliation")
    lines.append("")
    lines.append("```")
    lines.append(f"dataset_records ({total}) = source_answerable_true ({true_count}) "
                 f"+ source_answerable_false ({false_count}) "
                 f"+ no_gold_files ({no_gold}) = {sum_parts}")
    lines.append(f"  => {'PASS' if check1_ok else 'FAIL'}")
    lines.append("```")
    lines.append("")

    # Check 2: eligible_records <= total_records
    check2_ok = eligible <= total
    lines.append("## Retrieval Layer Scope")
    lines.append("")
    lines.append("```")
    lines.append(f"retrieval_layer_records ({eligible}) <= dataset_records ({total})")
    lines.append(f"  => {'PASS' if check2_ok else 'FAIL'}")
    lines.append("```")
    lines.append("")

    # Check 3: index_retrieval_scored_records <= retrieval_layer_records
    # The scored records are the n from overall metrics of each baseline
    b0_key = None
    b1_key = None
    for k in metrics:
        if k.startswith("b0"):
            b0_key = k
        elif k.startswith("b1"):
            b1_key = k

    lines.append("## Scored Records Scope")
    lines.append("")
    lines.append("```")
    for bkey in [b0_key, b1_key]:
        if bkey is None:
            continue
        bl = metrics[bkey]
        scored_n = bl.get("overall", {}).get("n", 0)
        check3_ok = scored_n <= eligible
        lines.append(f"{bkey}.overall.n ({scored_n}) <= "
                     f"retrieval_layer_records ({eligible})")
        lines.append(f"  => {'PASS' if check3_ok else 'FAIL'}")
    lines.append("```")
    lines.append("")

    return lines


def _section_d() -> list[str]:
    """Section D: Caveats."""
    lines: list[str] = []
    lines.append("# Section D: Caveats")
    lines.append("")
    lines.append("1. **Single-repo pilot.** All metrics are computed on a single "
                 "repository (ruoyi-vue). Results may not generalize to other "
                 "codebases, languages, or project structures.")
    lines.append("")
    lines.append("2. **Text-search baselines only.** B0 (ripgrep) and B1 (SQLite "
                 "keyword search) are text-matching baselines. They do not use "
                 "vector retrieval, query rewriting, or LLM-assisted search. "
                 "These results represent a lower bound on retrieval capability.")
    lines.append("")
    lines.append("3. **File-level matching.** Metrics measure whether any gold "
                 "file appears in the top-k results. They do not measure "
                 "line-level precision, entity-level recall, or whether the "
                 "retrieved file contains the relevant code at the correct "
                 "location.")
    lines.append("")
    lines.append("4. **Small sample size.** The pilot dataset has a limited "
                 "number of records. Group-level breakdowns have very small "
                 "n values, making point estimates unstable.")
    lines.append("")
    lines.append("5. **Token extraction bias.** Both baselines use whitespace/"
                 "punctuation-based token extraction, which systematically "
                 "disadvantages Chinese-language queries due to the lack of "
                 "inter-word spaces in Chinese text.")
    lines.append("")
    lines.append("6. **Offline evaluation.** These are offline metrics computed "
                 "against a fixed gold set. They do not reflect interactive "
                 "Agent performance where users can refine queries.")
    lines.append("")

    return lines


# =====================================================================
# Main
# =====================================================================


def generate_report(
    metrics_path: Path,
    dataset_path: Path,
    output_path: Path,
) -> int:
    """Generate the Markdown report. Returns 0 on success, 1 on error."""

    # Load metrics
    with open(metrics_path, "r", encoding="utf-8") as fh:
        metrics = _normalize_metrics(json.load(fh))

    # Verify SHA-256
    expected_sha = metrics.get("dataset_sha256", "")
    actual_sha = _sha256_file(dataset_path)

    if expected_sha and actual_sha != expected_sha:
        print(
            f"ERROR: Dataset SHA-256 mismatch.\n"
            f"  Expected (from metrics JSON): {expected_sha}\n"
            f"  Actual   (computed from file): {actual_sha}\n"
            f"Report generation refused.",
            file=sys.stderr,
        )
        return 1

    # Load dataset records
    dataset_records = _load_jsonl(dataset_path)

    # Build report
    report_lines: list[str] = []

    # Title
    report_lines.append("# ResearchCode-Agent Evaluation Report")
    report_lines.append("")
    report_lines.append(f"**Dataset SHA-256**: `{actual_sha}`")
    report_lines.append("")
    ts = metrics.get("timestamp", "N/A")
    report_lines.append(f"**Generated**: {ts}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # Sections
    report_lines.extend(_section_a(metrics, dataset_records, dataset_path))
    report_lines.extend(_section_b(metrics))
    report_lines.extend(_section_c(metrics))
    report_lines.extend(_section_d())

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(report_lines))
        fh.write("\n")

    print(f"Report written to {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown evaluation report from metrics JSON."
    )
    parser.add_argument(
        "--metrics", required=True, type=Path,
        help="Path to the metrics JSON file.",
    )
    parser.add_argument(
        "--dataset", required=True, type=Path,
        help="Path to the dataset JSONL file.",
    )
    parser.add_argument(
        "--output", required=True, type=Path,
        help="Path for the output Markdown report.",
    )
    args = parser.parse_args(argv)

    if not args.metrics.is_file():
        print(f"ERROR: Metrics file not found: {args.metrics}", file=sys.stderr)
        return 1
    if not args.dataset.is_file():
        print(f"ERROR: Dataset file not found: {args.dataset}", file=sys.stderr)
        return 1

    return generate_report(args.metrics, args.dataset, args.output)


if __name__ == "__main__":
    sys.exit(main())
