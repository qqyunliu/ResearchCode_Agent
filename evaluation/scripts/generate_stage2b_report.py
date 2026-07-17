"""Render a compact Stage 2B Markdown report exclusively from metrics JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _value(value: Any) -> str:
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def _metric(item: Mapping[str, Any], name: str) -> str:
    return _value(item.get(name, "N/A"))


def render_report(metrics: Mapping[str, Any]) -> str:
    identity = metrics.get("identity", {})
    environment = metrics.get("environment", {})
    graph = metrics.get("graph", {})
    b5 = metrics.get("agent", {}).get("B5", {})
    stability = metrics.get("stability", {})
    degeneracy = metrics.get("diagnostics", {}).get("hybrid_degeneracy", {})
    costs = metrics.get("costs", {})
    events = costs.get("response_events", {})
    lines = [
        "# Stage 2B Evaluation Report", "",
        "## Scope and identity", "",
        f"- Dataset records: {metrics.get('dataset', {}).get('records', 'N/A')}",
        f"- Dataset SHA-256: `{identity.get('dataset_sha256', 'N/A')}`",
        f"- Repository commit: `{identity.get('repo_commit', 'N/A')}`",
        f"- Repositories: {', '.join(metrics.get('dataset', {}).get('repositories', [])) or 'N/A'}",
        "", "## Environment", "",
        "| Item | Recorded value |", "|---|---|",
        f"| Models observed | {', '.join(events.get('models', [])) or 'N/A'} |",
        f"| Python | {_value(environment.get('python', {}).get('value', 'N/A'))} |",
        f"| Qdrant mode | {_value(environment.get('qdrant_mode', {}).get('value', 'N/A'))} |",
        f"| Retrieval top-k | {_value((environment.get('retrieval_config') or {}).get('top_k', 'N/A'))} |",
        "", "## B0-B5 summary", "",
        "| Method | n | Main deterministic result |", "|---|---:|---|",
    ]
    for variant in ("B0", "B1"):
        item = metrics.get("baselines", {}).get(variant, {})
        if item.get("status") == "comparable":
            lines.append(f"| {variant} | {_metric(item, 'n')} | File Recall@10={_metric(item, 'recall@10')} |")
        else:
            lines.append(f"| {variant} | N/A | Not comparable: {item.get('reason', 'raw evidence unavailable')} |")
    for variant in ("B2", "B3"):
        item = metrics.get("retrieval", {}).get(variant, {}).get("file", {})
        lines.append(f"| {variant} | {_metric(item, 'n')} | File Recall@10={_metric(item, 'recall@10')} |")
    b4 = graph.get("B4", {})
    lines.append(
        f"| B4 | {_metric(b4, 'n')} | Node P/R={_metric(b4, 'node_precision')}/{_metric(b4, 'node_recall')}; "
        f"edge P/R={_metric(b4, 'edge_precision')}/{_metric(b4, 'edge_recall')} |"
    )
    citations = b5.get("citation_details", {})
    lines.append(
        f"| B5 | {_metric(b5.get('routing', {}), 'n')} | Routing accuracy={_metric(b5.get('routing', {}), 'accuracy')}; "
        f"evidence citation P/R={_metric(citations, 'precision')}/{_metric(citations, 'recall')}; "
        f"ID/path validity={_metric(citations, 'citation_id_validity_rate')}/{_metric(citations, 'path_validity_rate')} |"
    )

    b2b3 = degeneracy.get("B2_vs_B3", {})
    a234 = degeneracy.get("A2_vs_A3_vs_A4", {})
    lines.extend(["", "## Retrieval degeneracy check", ""])
    if degeneracy.get("hybrid_comparison_valid") is False:
        lines.append(
            "The hybrid comparison is not valid for attributing improvement: "
            f"{degeneracy.get('reason', 'the variants degenerated to the same ranking')}."
        )
    else:
        lines.append("The compared retrieval variants produced distinguishable rankings.")
    lines.extend([
        "", "| Comparison | n | Identical Top-10 rate |", "|---|---:|---:|",
        f"| B2 vs B3 | {b2b3.get('n', 0)} | {_metric(b2b3, 'identical_top10_rate')} |",
        f"| A2 vs A3 vs A4 | {a234.get('n', 0)} | {_metric(a234, 'all_identical_top10_rate')} |",
    ])

    lines.extend(["", "## Graph depth ablation", "", "| Variant | n | Node precision | Node recall | Edge precision | Edge recall |", "|---|---:|---:|---:|---:|---:|"])
    for variant in ("A5", "A6", "B4"):
        item = graph.get(variant, {})
        lines.append(
            f"| {variant} | {_metric(item, 'n')} | {_metric(item, 'node_precision')} | {_metric(item, 'node_recall')} | "
            f"{_metric(item, 'edge_precision')} | {_metric(item, 'edge_recall')} |"
        )
    a6 = graph.get("A6", {})
    if b4.get("node_recall") == a6.get("node_recall") and b4.get("edge_recall") == a6.get("edge_recall"):
        lines.append(
            f"\nB4 (n={b4.get('n', 0)}) and A6 (n={a6.get('n', 0)}) have the same node and edge recall; "
            "there is no measured depth-2 gain on this Pilot."
        )

    lines.extend(["", "## Ablations", ""])
    for name in sorted(metrics.get("ablations", {})):
        item = metrics["ablations"][name]
        suffix = f": {item.get('reason')}" if item.get("reason") else ""
        lines.append(f"- {name}: `{item.get('status', 'unknown')}`{suffix}")

    lines.extend(["", "## Per-variant latency", ""])
    for variant in ("B2", "B3", "B4", "A1", "A2", "A3", "A4", "A5", "A6"):
        latency = metrics.get("retrieval", {}).get(variant, {}).get("latency_seconds")
        if latency is None:
            latency = graph.get(variant, {}).get("latency_seconds", {})
        lines.append(f"- {variant}: p50={_metric(latency, 'p50')}s; p95={_metric(latency, 'p95')}s")
    for variant in ("B5", "A8"):
        latency = metrics.get("agent", {}).get(variant, {}).get("latency_seconds", {})
        lines.append(f"- {variant}: p50={_metric(latency, 'p50')}s; p95={_metric(latency, 'p95')}s")

    repair = b5.get("repair", {})
    lines.extend([
        "", "## Stability, refusal, and repair", "",
        "| Measure | Value |", "|---|---:|",
        f"| Stability questions | {stability.get('n_questions', 0)} |",
        f"| Exact answer-hash agreement | {_metric(stability, 'answer_hash_agreement_rate')} |",
        f"| reference Jaccard | {_metric(stability, 'reference_jaccard_mean')} |",
        f"| Graph-node Jaccard | {_metric(stability, 'graph_node_jaccard_mean')} |",
    ])
    if stability.get("semantic_similarity_evaluated") is False:
        lines.append("\nsemantic similarity was not evaluated; hash disagreement does not by itself prove semantic disagreement.")
    refusal = b5.get("refusal", {})
    lines.extend([
        "", "| Refusal/uncertainty population | n | Rate |", "|---|---:|---:|",
        f"| Source-unanswerable (refusal detection) | {refusal.get('source_unanswerable_n', 0)} | {_metric(refusal, 'source_unanswerable_refusal_detection_rate')} |",
        f"| Source-answerable overall (over-refusal) | {refusal.get('source_answerable_n', 0)} | {_metric(refusal, 'source_answerable_over_refusal_rate')} |",
        f"| Source-answerable, system full (over-refusal) | {refusal.get('source_answerable_full_n', 0)} | {_metric(refusal, 'source_answerable_full_over_refusal_rate')} |",
        f"| Source-answerable partial/insufficient (over-refusal) | {refusal.get('source_answerable_partial_or_insufficient_n', 0)} | {_metric(refusal, 'source_answerable_partial_or_insufficient_over_refusal_rate')} |",
        f"| Uncertainty disclosure expected | {refusal.get('expected_uncertainty_n', 0)} | {_metric(refusal, 'uncertainty_compliance_rate')} |",
        "", "| Repair population | n | Attempted | Succeeded | Failed |", "|---|---:|---:|---:|---:|",
    ])
    for label, key in (("B5 run 0", "run0"), ("B5 all scheduled runs", "all_schedule")):
        item = repair.get(key, {})
        lines.append(f"| {label} | {item.get('population_n', 'N/A')} | {item.get('attempted', 'N/A')} | {item.get('succeeded', 'N/A')} | {item.get('failed', 'N/A')} |")

    usage = costs.get("usage", {})
    lines.extend([
        "", "## Cost evidence", "",
        f"- Provider attempts recorded: {events.get('attempts', 'N/A')}",
        f"- Total tokens recorded: {usage.get('total_tokens', events.get('usage', {}).get('total_tokens', 'N/A'))}",
        f"- Monetary cost: `{costs.get('monetary_cost', {}).get('status', 'unknown')}` - {costs.get('monetary_cost', {}).get('reason', 'pricing not pinned')}",
        "", "## Methodology boundary", "",
        "An LLM judge was not used. Semantic answer correctness, required-claim coverage, and hallucination rate were not measured. "
        "ID/path validity only checks whether cited identifiers and paths are structurally valid; it is shown next to evidence precision/recall and must not be read as factual correctness.",
        "A source-answerable partial/insufficient case should provide a qualified partial answer plus uncertainty; it is not an expected-refusal case.",
        "", "## Limitations", "",
    ])
    for limitation in metrics.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.extend([
        "- This Pilot is based on a single development repository and does not establish cross-repository generalization.",
        "- Temperature-zero model calls reduce but do not eliminate nondeterminism.", "",
    ])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Stage 2B Markdown report from metrics JSON")
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(metrics), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
