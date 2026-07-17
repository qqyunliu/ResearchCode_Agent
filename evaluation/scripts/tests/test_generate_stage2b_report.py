from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def metrics_fixture() -> dict:
    return {
        "identity": {"dataset_sha256": "a" * 64, "repo_commit": "b" * 40},
        "dataset": {"records": 36, "repositories": ["ruoyi-vue"]},
        "baselines": {"B0": {"recall@10": 0.2}, "B1": {"recall@10": 0.4}},
        "retrieval": {
            "B2": {"file": {"recall@10": 0.5}, "latency_seconds": {"p50": 0.1, "p95": 0.2}},
            "B3": {"file": {"recall@10": 0.6}, "latency_seconds": {"p50": 0.3, "p95": 0.4}},
        },
        "graph": {"B4": {"node_recall": 0.7, "edge_recall": 0.6}},
        "agent": {"B5": {"routing": {"accuracy": 0.8}, "citation_validity_rate": 0.9, "latency_seconds": {"p50": 0.5, "p95": 0.9}}},
        "stability": {"n_questions": 8, "answer_hash_agreement_rate": 0.75},
        "ablations": {
            "A7": {"status": "not_executable", "reason": "no multi-turn gold"},
            "A9": {"status": "not_executable", "reason": "no fair switch"},
        },
        "costs": {
            "provider_counters": {},
            "latency_seconds": {"retrieval": 1.0},
            "response_events": {"attempts": 2, "usage": {"total_tokens": 21}, "models": ["m-v1"]},
            "monetary_cost": {"status": "unknown", "reason": "pricing not pinned"},
        },
        "environment": {"repository_commit": "b", "dataset_sha256": "a", "retrieval_config": {"top_k": 10}},
        "methodology": {"llm_judge_used": False},
        "limitations": ["single development repository", "static analysis is best-effort"],
    }


def test_report_is_generated_only_from_metrics_and_states_limits() -> None:
    from generate_stage2b_report import render_report

    report = render_report(metrics_fixture())

    assert "Stage 2B" in report
    assert "B0" in report and "B5" in report
    assert "not_executable" in report
    assert "single development repository" in report
    assert "does not establish cross-repository generalization" in report
    assert "LLM judge" in report and "not used" in report
    assert "pricing not pinned" in report
    assert "m-v1" in report
    assert "Environment" in report
    assert "B2: p50=0.1000s; p95=0.2000s" in report
    assert "B5: p50=0.5000s; p95=0.9000s" in report


def test_report_cli_reads_metrics_json_and_writes_requested_path(tmp_path: Path) -> None:
    from generate_stage2b_report import main

    source = tmp_path / "metrics.json"
    target = tmp_path / "report.md"
    source.write_text(json.dumps(metrics_fixture()), encoding="utf-8")

    assert main(["--metrics", str(source), "--output", str(target)]) == 0
    assert target.read_text(encoding="utf-8").startswith("# Stage 2B")


def test_report_discloses_degeneracy_stability_and_unmeasured_boundaries() -> None:
    from generate_stage2b_report import render_report

    metrics = metrics_fixture()
    metrics["diagnostics"] = {
        "hybrid_degeneracy": {
            "B2_vs_B3": {"n": 27, "identical_top10_rate": 1.0},
            "A2_vs_A3_vs_A4": {"n": 27, "all_identical_top10_rate": 1.0},
            "hybrid_comparison_valid": False,
            "reason": "keyword branch returned zero hits",
        }
    }
    metrics["graph"] = {
        "B4": {"n": 12, "node_precision": 0.4, "node_recall": 0.5, "edge_precision": 0.6, "edge_recall": 0.7},
        "A6": {"n": 12, "node_precision": 0.4, "node_recall": 0.5, "edge_precision": 0.6, "edge_recall": 0.7},
    }
    metrics["agent"]["B5"].update({
        "citation_details": {"citation_id_validity_rate": 1.0, "path_validity_rate": 1.0, "precision": 0.2, "recall": 0.3},
        "repair": {"run0": {"attempted": 2, "succeeded": 1, "failed": 1}, "all_schedule": {"attempted": 6, "succeeded": 2, "failed": 4}},
        "refusal": {
            "source_unanswerable_n": 8,
            "source_unanswerable_refusal_detection_rate": 0.375,
            "source_answerable_n": 28,
            "source_answerable_over_refusal_rate": 0.0714,
            "source_answerable_full_n": 22,
            "source_answerable_full_over_refusal_rate": 0.0,
            "source_answerable_partial_or_insufficient_n": 6,
            "source_answerable_partial_or_insufficient_over_refusal_rate": 0.3333,
            "expected_uncertainty_n": 14,
            "uncertainty_compliance_rate": 0.5,
        },
    })
    metrics["stability"] = {
        "n_questions": 8,
        "answer_hash_agreement_rate": 0.0,
        "reference_jaccard_mean": 1.0,
        "graph_node_jaccard_mean": 1.0,
        "semantic_similarity_evaluated": False,
    }

    report = render_report(metrics)

    assert "hybrid comparison is not valid" in report.lower()
    assert "keyword branch returned zero hits" in report
    assert "B4" in report and "n=12" in report and "A6" in report
    assert "no measured depth-2 gain" in report.lower()
    assert "ID/path validity" in report
    assert "answer-hash agreement" in report and "0.0000" in report
    assert "reference Jaccard" in report and "1.0000" in report
    assert "semantic similarity was not evaluated" in report
    assert "required-claim coverage" in report and "hallucination rate" in report
    assert "Source-unanswerable (refusal detection)" in report
    assert "Source-answerable overall (over-refusal)" in report
    assert "Source-answerable partial/insufficient" in report
    assert "```json" not in report
