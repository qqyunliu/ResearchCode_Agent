from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def case(question_id: str, *, answerable: bool = True) -> dict:
    return {
        "dataset_version": "1.4",
        "question_id": question_id,
        "repo_id": "repo",
        "commit_sha": "b" * 40,
        "gold_status": "machine_verified",
        "execution_status": "executable",
        "annotation": {"review_status": "accepted"},
        "evaluation_layers": ["routing", "retrieval", "trace_chain", "answer_citation"],
        "source_answerable": answerable,
        "system_answerable": "full" if answerable else "insufficient",
        "expected_task_type": "TRACE_CHAIN" if answerable else "CODE_QA",
        "language": "en",
        "gold_entities": (
            [
                {"stable_entity_key": "e1", "file_path": "f1.java", "relevance": "must_recall", "indexed_in_system": True},
                {"stable_entity_key": "e2", "file_path": "f2.java", "relevance": "must_recall", "indexed_in_system": True},
            ]
            if answerable
            else []
        ),
        "gold_files": [
            {"file_path": "must.java", "category": "must_change"},
            {"file_path": "never.java", "category": "should_not_change"},
        ],
        "gold_nodes": (
            [
                {"stable_entity_key": "e1", "order": 0, "indexed_in_system": True},
                {"stable_entity_key": "e2", "order": 1, "indexed_in_system": True},
            ]
            if answerable
            else []
        ),
        "gold_edges": (
            [{"source_key": "e1", "target_key": "e2", "relation_type": "CALLS_METHOD", "indexed_in_system": True}]
            if answerable
            else []
        ),
        "expected_uncertainties": [] if answerable else [{"condition": "missing"}],
        "required_claims": ([{"evidence_ranges": [{"file_path": "f1.java", "start_line": 1, "end_line": 3}]}] if answerable else []),
    }


def retrieval_record(question_id: str, variant: str, *, answerable: bool = True) -> dict:
    record = {
        "question_id": question_id,
        "variant": variant,
        "run_index": 0,
        "status": "ok",
        "hits": (
            [
                {"stable_entity_key": "e1", "file_path": "f1.java"},
                {"stable_entity_key": "x", "file_path": "noise.java"},
                {"stable_entity_key": "e2", "file_path": "f2.java"},
            ]
            if answerable
            else [{"stable_entity_key": "x", "file_path": "noise.java"}]
        ),
        "graph_nodes": (
            [
                {"stable_entity_key": "e1"},
                {"stable_entity_key": "x"},
            ]
            if variant in {"B4", "A5", "A6"}
            else []
        ),
        "graph_edges": (
            [
                {"source_stable_entity_key": "e1", "target_stable_entity_key": "e2", "relation_type": "CALLS_METHOD"},
                {"source_stable_entity_key": "e1", "target_stable_entity_key": "x", "relation_type": "CALLS_METHOD"},
            ]
            if variant in {"B4", "A5", "A6"}
            else []
        ),
        "latency_seconds": 0.2,
    }
    if variant in {"B3", "A1", "A2", "A3", "A4"}:
        record["branch_diagnostics"] = {
            "vector_candidate_count": 2,
            "keyword_candidate_count": 1,
            "overlap_count": 1,
            "keyword_only_count": 0,
            "top10_changed_from_vector": False,
        }
    return record


def agent_record(question_id: str, variant: str, run_index: int, *, answerable: bool = True) -> dict:
    return {
        "question_id": question_id,
        "variant": variant,
        "run_index": run_index,
        "status": "ok",
        "expected_task_type": "TRACE_CHAIN" if answerable else "CODE_QA",
        "planned_task_type": "TRACE_CHAIN" if answerable else "CHANGE_PLAN",
        "answer": "answer [1]" if answerable else "Insufficient evidence.",
        "references": (
            [{"stable_entity_key": "e1", "file_path": "f1.java", "start_line": 1, "end_line": 3}]
            if answerable
            else []
        ),
        "graph_nodes": [{"stable_entity_key": "e1"}] if answerable else [],
        "graph_edges": (
            [{"source_stable_entity_key": "e1", "target_stable_entity_key": "e2", "relation_type": "CALLS_METHOD"}]
            if answerable
            else []
        ),
        "uncertainties": [] if answerable else ["missing"],
        "citation_validation": {"is_valid": True, "invalid_citations": [], "invalid_paths": []},
        "provider_call_deltas": {"agent_llm": 2 if answerable else 0, "query_embedding": 1, "rewrite_llm": 0},
        "repair_attempted_inferred": answerable,
        "guard_failure_inferred": False,
        "wall_latency_seconds": 0.5,
        "llm_response_events": (
            [
                {"attempt_id": f"{question_id}-{variant}-{run_index}-initial", "phase": "initial", "requested_model": "m", "returned_model": "m-v1", "usage_available": True, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "provider_latency_seconds": 0.3, "error": None},
                *([{"attempt_id": f"{question_id}-{variant}-{run_index}-repair", "phase": "repair", "requested_model": "m", "returned_model": "m-v1", "usage_available": True, "prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6, "provider_latency_seconds": 0.2, "error": None}] if answerable else []),
            ]
        ),
    }


def fixture_inputs():
    dataset = [case("q1"), case("q2", answerable=False)]
    retrieval = [
        retrieval_record(qid, variant, answerable=(qid == "q1"))
        for qid in ("q1", "q2")
        for variant in ("B2", "B3", "B4", "A1", "A2", "A3", "A4", "A5", "A6")
    ]
    agent = [
        agent_record("q1", "B5", run_index)
        for run_index in (0, 1, 2)
    ] + [
        agent_record("q1", "A8", 0),
        agent_record("q2", "B5", 0, answerable=False),
        agent_record("q2", "A8", 0, answerable=False),
    ]
    baseline = {
        "baselines": {
            "b0_rgrep": {"overall": {"n": 1, "recall@10": 0.2}},
            "b1_keyword": {"overall": {"n": 1, "recall@10": 0.4}},
        }
    }
    return dataset, retrieval, agent, baseline


def test_retrieval_entity_file_and_source_unanswerable_metrics() -> None:
    from compute_stage2b_metrics import compute_metrics

    metrics = compute_metrics(*fixture_inputs(), strict=False, snapshot_files={"f1.java", "f2.java"})
    b2 = metrics["retrieval"]["B2"]

    assert b2["entity"]["recall@1"] == 0.5
    assert b2["entity"]["recall@5"] == 1.0
    assert b2["entity"]["mrr"] == 1.0
    assert b2["entity"]["zero_hit_rate"] == 0.0
    assert b2["file"]["recall@1"] == 0.5
    assert metrics["diagnostics"]["source_unanswerable"]["B2"] == {
        "n": 1,
        "nonempty_hit_rate": 1.0,
        "error_rate": 0.0,
    }
    assert set(metrics["retrieval"]) == {"B2", "B3", "A1", "A2", "A3", "A4"}


def test_graph_metrics_and_chain_diagnostics() -> None:
    from compute_stage2b_metrics import compute_metrics

    graph = compute_metrics(*fixture_inputs(), strict=False, snapshot_files={"f1.java", "f2.java"})["graph"]["B4"]

    assert graph["node_precision"] == 0.5
    assert graph["node_recall"] == 0.5
    assert graph["edge_precision"] == 0.5
    assert graph["edge_recall"] == 1.0
    assert graph["chain_diagnostics"]["complete_chain_rate"] == 0.0
    assert graph["chain_diagnostics"]["non_gold_edge_rate"] == 0.5
    assert graph["chain_diagnostics"]["unsupported_stored_edge_rate"] == 0.0
    assert graph["chain_diagnostics"]["exact_ordered_chain_match"] == "not_computable_from_unordered_evidence"


def test_agent_metrics_are_deterministic_without_llm_judge() -> None:
    from compute_stage2b_metrics import compute_metrics

    metrics = compute_metrics(*fixture_inputs(), strict=False, snapshot_files={"f1.java", "f2.java"})
    b5 = metrics["agent"]["B5"]

    assert b5["routing"]["accuracy"] == 0.5
    assert b5["references"]["entity_recall"] == 0.5
    assert b5["references"]["entity_precision"] == 1.0
    assert b5["graph"]["node_recall"] == 0.5
    assert b5["graph"]["edge_recall"] == 1.0
    assert b5["citation_validity_rate"] == 1.0
    assert b5["path_validity_rate"] == 1.0
    assert b5["refusal"]["correct_refusal_rate"] == 1.0
    assert b5["repair"]["attempt_rate"] == 0.5
    assert b5["provider"]["record_failure_rate"] == 0.0
    assert metrics["methodology"]["llm_judge_used"] is False


def test_stability_baselines_costs_and_unsupported_ablations() -> None:
    from compute_stage2b_metrics import compute_metrics

    metrics = compute_metrics(
        *fixture_inputs(),
        retrieval_metadata={"provider_counters": {"embedding_sdk_create_attempts": {"calls": 4}}},
        agent_metadata={"provider_counters": {"agent_llm_sdk_create_attempts": {"calls": 8}}},
        strict=False,
        snapshot_files={"f1.java", "f2.java"},
    )

    assert metrics["stability"]["n_questions"] == 1
    assert metrics["stability"]["reference_jaccard_mean"] == 1.0
    assert metrics["stability"]["answer_hash_agreement_rate"] == 1.0
    assert metrics["baselines"]["B0"]["status"] == "not_comparable"
    assert metrics["baselines"]["B1"]["status"] == "not_comparable"
    assert metrics["ablations"]["A7"]["status"] == "not_executable"
    assert metrics["ablations"]["A9"]["status"] == "not_executable"
    assert metrics["costs"]["provider_counters"]["agent"]["agent_llm_sdk_create_attempts"]["calls"] == 8
    assert metrics["costs"]["usage"]["token_usage"] == "recorded"
    assert metrics["costs"]["usage"]["total_tokens"] == 114


def test_identity_mismatch_is_rejected() -> None:
    from compute_stage2b_metrics import validate_artifact_identity

    records = [
        {"run_id": "run", "dataset_sha256": "a", "repo_commit": "b"},
        {"run_id": "other", "dataset_sha256": "a", "repo_commit": "b"},
    ]
    with pytest.raises(ValueError, match="identity"):
        validate_artifact_identity(records)


def test_file_recall_deduplicates_ranked_file_paths() -> None:
    from compute_stage2b_metrics import compute_metrics

    dataset = [case("q1")]
    hits = [
        {"stable_entity_key": f"noise-{index}", "file_path": "f1.java"}
        for index in range(5)
    ] + [{"stable_entity_key": "e2", "file_path": "f2.java"}]
    raw = [{**retrieval_record("q1", "B2"), "hits": hits}]

    b2 = compute_metrics(dataset, raw, [], {}, strict=False)["retrieval"]["B2"]

    assert b2["file"]["recall@5"] == 1.0
    assert b2["entity"]["recall@5"] == 0.0


def test_formal_gate_rejects_noncanonical_dataset_and_incomplete_schedule() -> None:
    from compute_stage2b_metrics import select_stability_question_ids, validate_formal_artifacts

    tasks = ("CODE_QA", "TRACE_CHAIN", "CHANGE_PLAN")
    dataset = []
    for index in range(36):
        answerable = index % 5 != 0
        dataset.append({
            **case(f"q{index:02d}", answerable=answerable),
            "expected_task_type": tasks[index % len(tasks)],
            "language": "zh" if index % 2 else "en",
            "difficulty": ("hard", "medium", "easy")[index % 3],
        })
    retrieval = [
        retrieval_record(str(item["question_id"]), variant, answerable=bool(item["source_answerable"]))
        for item in dataset
        for variant in (*(("B2", "B3", "A1", "A2", "A3", "A4")), *(("B4", "A5", "A6")))
    ]
    stability_ids = select_stability_question_ids(dataset)
    by_id = {str(item["question_id"]): item for item in dataset}
    agent = [
        agent_record(str(item["question_id"]), variant, 0, answerable=bool(item["source_answerable"]))
        for item in dataset for variant in ("B5", "A8")
    ] + [
        agent_record(question_id, "B5", run_index, answerable=bool(by_id[question_id]["source_answerable"]))
        for question_id in stability_ids for run_index in (1, 2)
    ]
    identities = {
        "run_id": "retrieval-run", "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40, "config_fingerprint": "r" * 64,
        "db_sha256": "d" * 64, "snapshot_sha256": "s" * 64,
    }
    retrieval = [{**record, **identities} for record in retrieval]
    agent_identity = {**identities, "run_id": "agent-run", "config_fingerprint": "g" * 64}
    agent = [{**record, **agent_identity} for record in agent]
    retrieval_meta = {**identities, "status": "completed", "records_written": len(retrieval)}
    agent_meta = {**agent_identity, "status": "completed", "records_written": len(agent), "stability_subset": {"question_ids": stability_ids}}

    validate_formal_artifacts(dataset, retrieval, agent, retrieval_meta, agent_meta, "a" * 64)
    with pytest.raises(ValueError, match="canonical"):
        validate_formal_artifacts([{**item, "gold_status": "machine_proposed"} for item in dataset], retrieval, agent, retrieval_meta, agent_meta, "a" * 64)
    with pytest.raises(ValueError, match="schedule"):
        validate_formal_artifacts(dataset, retrieval[:-1], agent, retrieval_meta, agent_meta, "a" * 64)

    only_run_zero = [record for record in agent if record["run_index"] == 0]
    empty_subset_meta = {**agent_meta, "records_written": len(only_run_zero), "stability_subset": {"question_ids": []}}
    with pytest.raises(ValueError, match="stability subset"):
        validate_formal_artifacts(dataset, retrieval, only_run_zero, retrieval_meta, empty_subset_meta, "a" * 64)


def test_retrieval_only_formal_gate_uses_metadata_selected_schedule_and_reports_core_metrics() -> None:
    from compute_stage2b_metrics import compute_metrics, validate_formal_artifacts

    dataset = [
        {
            **case(f"q{index:02d}", answerable=index % 5 != 0),
            "expected_task_type": ("CODE_QA", "TRACE_CHAIN", "CHANGE_PLAN")[index % 3],
            "language": "zh" if index % 2 else "en",
            "difficulty": ("hard", "medium", "easy")[index % 3],
        }
        for index in range(36)
    ]
    selected = ("B2", "B3", "A1", "A2", "A3", "A4")
    identity = {
        "run_id": "selected-retrieval-run",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "config_fingerprint": "r" * 64,
        "db_sha256": "d" * 64,
        "snapshot_sha256": "s" * 64,
    }
    retrieval = [
        {
            **retrieval_record(
                str(item["question_id"]),
                variant,
                answerable=bool(item["source_answerable"]),
            ),
            **identity,
        }
        for item in dataset
        for variant in selected
    ]
    metadata = {
        **identity,
        "status": "completed",
        "records_written": 216,
        "selected_variants": list(selected),
        "provider_counters": {
            name: {
                "calls": 1,
                "successes": 1,
                "failures": 0,
                "latency_seconds": 0.1,
                "pending": 0,
                "unconfirmed": 0,
            }
            for name in (
                "embedding_sdk_create_attempts",
                "rewrite_llm_sdk_create_attempts",
            )
        },
        "provider_ledger_summary": {
            name: {"pending": 0, "unconfirmed": 0, "orphan": 0}
            for name in (
                "embedding_sdk_create_attempts",
                "rewrite_llm_sdk_create_attempts",
            )
        },
    }

    validate_formal_artifacts(
        dataset,
        retrieval,
        [],
        metadata,
        None,
        "a" * 64,
        retrieval_only=True,
    )
    with pytest.raises(ValueError, match="schedule"):
        validate_formal_artifacts(
            dataset,
            retrieval[:-1],
            [],
            metadata,
            None,
            "a" * 64,
            retrieval_only=True,
        )
    with pytest.raises(ValueError, match="selected_variants"):
        validate_formal_artifacts(
            dataset,
            retrieval,
            [],
            {**metadata, "selected_variants": ["B2"]},
            None,
            "a" * 64,
            retrieval_only=True,
        )

    metrics = compute_metrics(
        dataset,
        retrieval,
        [],
        {"dataset_sha256": "a" * 64, "baselines": {}},
        retrieval_metadata=metadata,
        agent_metadata=None,
        strict=True,
        dataset_sha256="a" * 64,
        retrieval_only=True,
    )
    for variant in selected:
        assert set(("recall@5", "recall@10", "mrr")) <= set(
            metrics["retrieval"][variant]["entity"]
        )

    error_records = [dict(record) for record in retrieval]
    error_records[0]["status"] = "error"
    with pytest.raises(ValueError, match="status"):
        validate_formal_artifacts(
            dataset, error_records, [], metadata, None, "a" * 64,
            retrieval_only=True,
        )

    missing_diagnostics = [dict(record) for record in retrieval]
    hybrid_index = next(
        index for index, record in enumerate(missing_diagnostics)
        if record["variant"] == "B3"
    )
    missing_diagnostics[hybrid_index].pop("branch_diagnostics")
    with pytest.raises(ValueError, match="branch_diagnostics"):
        validate_formal_artifacts(
            dataset, missing_diagnostics, [], metadata, None, "a" * 64,
            retrieval_only=True,
        )

    for field in ("pending", "unconfirmed"):
        corrupt_metadata = json.loads(json.dumps(metadata))
        corrupt_metadata["provider_counters"]["embedding_sdk_create_attempts"][field] = 1
        with pytest.raises(ValueError, match=field):
            validate_formal_artifacts(
                dataset, retrieval, [], corrupt_metadata, None, "a" * 64,
                retrieval_only=True,
            )
    corrupt_metadata = json.loads(json.dumps(metadata))
    corrupt_metadata["provider_ledger_summary"]["embedding_sdk_create_attempts"]["orphan"] = 1
    with pytest.raises(ValueError, match="orphan"):
        validate_formal_artifacts(
            dataset, retrieval, [], corrupt_metadata, None, "a" * 64,
            retrieval_only=True,
        )

    missing_counter_metadata = json.loads(json.dumps(metadata))
    del missing_counter_metadata["provider_counters"]["rewrite_llm_sdk_create_attempts"]["pending"]
    with pytest.raises(ValueError, match="pending"):
        validate_formal_artifacts(
            dataset, retrieval, [], missing_counter_metadata, None, "a" * 64,
            retrieval_only=True,
        )


def test_original_formal_mode_still_requires_complete_agent_artifacts() -> None:
    from compute_stage2b_metrics import compute_metrics

    with pytest.raises(ValueError, match="retrieval and agent metadata"):
        compute_metrics(
            [case("q1")],
            [],
            [],
            {"dataset_sha256": "a" * 64},
            retrieval_metadata={},
            agent_metadata=None,
            strict=True,
            dataset_sha256="a" * 64,
        )


def test_metrics_cli_retrieval_only_mode_allows_omitting_agent_artifacts() -> None:
    from compute_stage2b_metrics import build_parser, validate_metrics_mode_args

    required = [
        "--dataset", "dataset.jsonl",
        "--retrieval-raw", "retrieval.jsonl",
        "--baseline-metrics", "baseline.json",
        "--retrieval-metadata", "retrieval.metadata.json",
        "--snapshot-code-files", "code_files.json",
        "--snapshot-attestation", "attestation.json",
        "--output", "metrics.json",
    ]
    retrieval_only = build_parser().parse_args([*required, "--retrieval-only"])
    validate_metrics_mode_args(retrieval_only)

    complete = build_parser().parse_args(
        [
            *required,
            "--agent-raw", "agent.jsonl",
            "--agent-metadata", "agent.metadata.json",
        ]
    )
    validate_metrics_mode_args(complete)

    incomplete = build_parser().parse_args(required)
    with pytest.raises(ValueError, match="agent raw and metadata"):
        validate_metrics_mode_args(incomplete)


def test_baseline_sha_is_required_and_must_match() -> None:
    from compute_stage2b_metrics import validate_baseline_identity

    with pytest.raises(ValueError, match="dataset_sha256"):
        validate_baseline_identity({}, "a" * 64)
    with pytest.raises(ValueError, match="dataset_sha256"):
        validate_baseline_identity({"dataset_sha256": "b" * 64}, "a" * 64)


def test_retrieval_file_gold_excludes_change_plan_categories() -> None:
    from compute_stage2b_metrics import _gold_files, change_plan_file_gold

    sample = case("q")
    assert _gold_files(sample) == {"f1.java", "f2.java"}
    assert change_plan_file_gold(sample) == {
        "must_change": {"must.java"},
        "likely_change": set(),
        "context_only": set(),
        "should_not_change": {"never.java"},
    }


def test_citation_metrics_use_only_answer_citation_ids_and_fixed_paths() -> None:
    from compute_stage2b_metrics import citation_metrics

    cited = agent_record("q1", "B5", 0)
    uncited = {**cited, "answer": "answer without citation"}

    assert citation_metrics([cited], {"q1": case("q1")}, {"f1.java"})["precision"] == 1.0
    undefined = citation_metrics([uncited], {"q1": case("q1")}, {"f1.java"})
    assert undefined["eligible_citations"] == 0
    assert undefined["precision"] is None
    assert undefined["path_validity_rate"] is None


def test_response_events_drive_usage_model_failure_and_repair_metrics() -> None:
    from compute_stage2b_metrics import response_event_metrics

    events = agent_record("q1", "B5", 0)["llm_response_events"]
    summary = response_event_metrics(events)

    assert summary["attempts"] == 2
    assert summary["repair_attempts"] == 1
    assert summary["usage"]["total_tokens"] == 21
    assert summary["models"] == ["m-v1"]
    assert summary["failed_attempts"] == 0


def test_refusal_population_uses_source_unanswerability_not_system_partiality() -> None:
    from compute_stage2b_metrics import refusal_metrics

    sample = {**case("q1"), "source_answerable": True, "system_answerable": "insufficient", "expected_uncertainties": [{"condition": "gap"}]}
    record = {**agent_record("q1", "B5", 0), "answer": "Insufficient evidence.", "uncertainties": ["gap"]}

    result = refusal_metrics([record], {"q1": sample})

    assert result["source_unanswerable_n"] == 0
    assert result["source_answerable_n"] == 1
    assert result["source_answerable_over_refusal_rate"] == 1.0
    assert result["source_answerable_partial_or_insufficient_n"] == 1
    assert result["source_answerable_partial_or_insufficient_over_refusal_rate"] == 1.0
    assert result["uncertainty_compliance_rate"] == 1.0


def test_uncertainty_is_not_misclassified_as_explicit_refusal() -> None:
    from compute_stage2b_metrics import refusal_metrics

    sample = {
        **case("q1"),
        "source_answerable": True,
        "system_answerable": "insufficient",
        "expected_uncertainties": [{"condition": "one graph edge is missing"}],
    }
    qualified_answer = {
        **agent_record("q1", "B5", 0),
        "answer": "The controller is A [1], but one downstream edge is uncertain.",
        "uncertainties": ["one graph edge is missing"],
    }

    result = refusal_metrics([qualified_answer], {"q1": sample})

    assert result["source_answerable_over_refusal_rate"] == 0.0
    assert result["uncertainty_compliance_rate"] == 1.0


def test_refusal_detects_correct_chinese_and_structured_fallbacks() -> None:
    from compute_stage2b_metrics import refusal_metrics

    sample = {**case("q1", answerable=False), "source_answerable": False, "system_answerable": "insufficient"}
    chinese = {**agent_record("q1", "B5", 0), "answer": "证据不足，无法回答。", "uncertainties": []}
    fallback = {
        **agent_record("q1", "B5", 0),
        "answer": "",
        "uncertainties": [],
        "guard_failure_inferred": True,
    }

    assert refusal_metrics([chinese], {"q1": sample})["source_unanswerable_refusal_detection_rate"] == 1.0
    assert refusal_metrics([fallback], {"q1": sample})["source_unanswerable_refusal_detection_rate"] == 1.0


def test_refusal_metrics_separate_source_true_full_and_partial_strata() -> None:
    from compute_stage2b_metrics import refusal_metrics

    cases = {
        "u": {**case("u", answerable=False), "source_answerable": False},
        "f": {**case("f"), "source_answerable": True, "system_answerable": "full"},
        "p": {**case("p"), "source_answerable": True, "system_answerable": "insufficient", "expected_uncertainties": [{"condition": "gap"}]},
    }
    records = [
        {**agent_record("u", "B5", 0, answerable=False), "answer": "Cannot answer."},
        {**agent_record("f", "B5", 0), "answer": "Supported [1]", "uncertainties": []},
        {**agent_record("p", "B5", 0), "answer": "Partial answer [1]", "uncertainties": ["gap"]},
    ]

    result = refusal_metrics(records, cases)

    assert result["source_unanswerable_n"] == 1
    assert result["source_unanswerable_refusal_detection_rate"] == 1.0
    assert result["source_answerable_n"] == 2
    assert result["source_answerable_over_refusal_rate"] == 0.0
    assert result["source_answerable_full_n"] == 1
    assert result["source_answerable_partial_or_insufficient_n"] == 1


def test_repair_outcome_is_rederived_from_events_and_final_structured_state() -> None:
    from compute_stage2b_metrics import compute_metrics

    repaired = agent_record("q1", "B5", 0)
    repaired.update(repair_succeeded=False, repair_failed=False)
    failed = agent_record("q1", "B5", 0)
    failed.update(
        answer="The model answer did not pass evidence validation, so it was not returned.",
        uncertainties=["Evidence validation repair limit reached."],
        guard_failure_inferred=True,
        repair_succeeded=True,
        repair_failed=False,
    )
    metrics_ok = compute_metrics([case("q1")], [], [repaired], {}, strict=False)
    metrics_failed = compute_metrics([case("q1")], [], [failed], {}, strict=False)

    assert metrics_ok["agent"]["B5"]["repair"]["run0"]["succeeded"] == 1
    assert metrics_failed["agent"]["B5"]["repair"]["run0"]["failed"] == 1


def test_retrieval_degeneracy_is_detected_from_top10_keys() -> None:
    from compute_stage2b_metrics import compute_metrics

    dataset, retrieval, agent, baseline = fixture_inputs()
    metrics = compute_metrics(dataset, retrieval, agent, baseline, strict=False)

    diagnostic = metrics["diagnostics"]["hybrid_degeneracy"]
    assert diagnostic["B2_vs_B3"]["identical_top10_rate"] == 1.0
    assert diagnostic["A2_vs_A3_vs_A4"]["all_identical_top10_rate"] == 1.0
    assert diagnostic["hybrid_comparison_valid"] is False


def test_shared_file_baseline_requires_identity_and_uses_same_file_gold() -> None:
    from compute_stage2b_metrics import shared_file_baseline

    sample = case("q1")
    identity = {
        "dataset_sha256": "a" * 64, "repo_commit": "b" * 40,
        "config_fingerprint": "c" * 64, "run_id": "baseline-run",
    }
    raw = [{**retrieval_record("q1", "B0"), **identity}]
    result = shared_file_baseline("B0", raw, {"q1": sample}, identity["dataset_sha256"], identity["repo_commit"])

    assert result["status"] == "comparable"
    assert result["recall@10"] == 1.0
    assert shared_file_baseline("B0", [{**raw[0], "dataset_sha256": None}], {"q1": sample}, identity["dataset_sha256"], identity["repo_commit"])["status"] == "not_comparable"


def test_shared_file_baseline_accepts_full_schedule_but_scores_only_indexed_gold() -> None:
    from compute_stage2b_metrics import shared_file_baseline

    answerable = case("q1")
    diagnostic = case("q2", answerable=False)
    identity = {
        "dataset_sha256": "a" * 64, "repo_commit": "b" * 40,
        "config_fingerprint": "c" * 64, "run_id": "baseline-run",
    }
    raw = [
        {**retrieval_record("q1", "B0"), **identity},
        {**retrieval_record("q2", "B0", answerable=False), **identity},
    ]

    result = shared_file_baseline(
        "B0", raw, {"q1": answerable, "q2": diagnostic},
        identity["dataset_sha256"], identity["repo_commit"],
    )

    assert result["status"] == "comparable"
    assert result["n"] == 1


def test_shared_file_baseline_rejects_mixed_run_or_config_identity() -> None:
    from compute_stage2b_metrics import shared_file_baseline

    sample = case("q1")
    identity = {
        "dataset_sha256": "a" * 64, "repo_commit": "b" * 40,
        "config_fingerprint": "c" * 64, "run_id": "baseline-run",
    }
    raw = [{**retrieval_record("q1", "B0"), **identity}]
    assert shared_file_baseline(
        "B0", [{**raw[0], "config_fingerprint": None}], {"q1": sample},
        identity["dataset_sha256"], identity["repo_commit"],
    )["status"] == "not_comparable"


def _baseline_metadata(name: str, records: list[dict]) -> dict:
    import hashlib
    import json

    effective_config = {
        "contract_version": 1,
        "ranking_unit": "file",
        "top_k": 10,
        "variant": name,
    }
    fingerprint = hashlib.sha256(json.dumps(
        effective_config, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")).hexdigest()
    run_digest = hashlib.sha256(
        f"{'a' * 64}:{'b' * 40}:{fingerprint}".encode("ascii")
    ).hexdigest()[:16]
    return {
        "run_id": f"stage2b-{name.lower()}-{run_digest}",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "config_fingerprint": fingerprint,
        "variant": name,
        "run_index": 0,
        "effective_config": effective_config,
        "status": "completed",
        "records_written": len(records),
    }


def test_formal_baseline_gate_recomputes_fingerprint_and_binds_sidecar() -> None:
    from compute_stage2b_metrics import validate_baseline_artifact

    records = []
    for index in range(36):
        records.append({
            "question_id": f"q{index:02d}", "variant": "B0", "run_index": 0,
            "run_id": "baseline-run", "dataset_sha256": "a" * 64,
            "repo_commit": "b" * 40,
        })
    metadata = _baseline_metadata("B0", records)
    for record in records:
        for field in ("run_id", "config_fingerprint"):
            record[field] = metadata[field]

    validate_baseline_artifact(
        "B0", records, metadata, {record["question_id"] for record in records},
        "a" * 64, "b" * 40,
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda records, metadata: metadata.update(status="failed"), "completed"),
        (lambda records, metadata: metadata.update(records_written=35), "records_written"),
        (lambda records, metadata: records[0].update(run_id="other"), "identity"),
        (lambda records, metadata: metadata.update(config_fingerprint="f" * 64), "fingerprint"),
    ],
)
def test_formal_baseline_gate_rejects_untrusted_sidecar(
    mutation, message: str,
) -> None:
    from compute_stage2b_metrics import validate_baseline_artifact

    records = [{
        "question_id": f"q{index:02d}", "variant": "B1", "run_index": 0,
        "run_id": "baseline-run", "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
    } for index in range(36)]
    metadata = _baseline_metadata("B1", records)
    for record in records:
        for field in ("run_id", "config_fingerprint"):
            record[field] = metadata[field]
    mutation(records, metadata)

    with pytest.raises(ValueError, match=message):
        validate_baseline_artifact(
            "B1", records, metadata, {record["question_id"] for record in records},
            "a" * 64, "b" * 40,
        )


def test_metrics_cli_requires_metadata_for_supplied_baseline_raw() -> None:
    from compute_stage2b_metrics import validate_baseline_cli_pair

    with pytest.raises(ValueError, match="metadata"):
        validate_baseline_cli_pair("B0", Path("b0.jsonl"), None)


def test_snapshot_paths_are_bound_to_manifest_hash_and_commit(tmp_path: Path) -> None:
    import hashlib
    import json
    from compute_stage2b_metrics import validate_snapshot_binding

    manifest = tmp_path / "manifest.json"
    code_files = tmp_path / "code_files.json"
    code_files.write_text("[]", encoding="utf-8")
    code_sha = hashlib.sha256(code_files.read_bytes()).hexdigest()
    manifest.write_text(json.dumps({
        "commit_sha": "b" * 40,
        "artifacts": {"code_files": {"path": "code_files.json", "sha256": code_sha}},
    }), encoding="utf-8")
    metadata = {"snapshot_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(), "repo_commit": "b" * 40}

    validate_snapshot_binding(manifest, code_files, metadata, metadata)
    with pytest.raises(ValueError, match="hash"):
        validate_snapshot_binding(manifest, code_files, {**metadata, "snapshot_sha256": "0" * 64}, metadata)
    with pytest.raises(ValueError, match="commit"):
        validate_snapshot_binding(manifest, code_files, metadata, {**metadata, "repo_commit": "c" * 40})
    code_entities = tmp_path / "code_entities.json"
    code_entities.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="code_files"):
        validate_snapshot_binding(manifest, code_entities, metadata, metadata)
    code_files.write_text('[{"file_path":"tampered"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="code_files.*hash"):
        validate_snapshot_binding(manifest, code_files, metadata, metadata)


def test_snapshot_v3_attestation_binds_every_export_and_original_manifest(tmp_path: Path) -> None:
    import hashlib
    import json
    from compute_stage2b_metrics import generate_snapshot_attestation, validate_snapshot_attestation

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"commit_sha": "b" * 40}), encoding="utf-8")
    for name in ("code_files.json", "code_entities.json", "code_relations.json", "frontend_diagnostics.json", "scan_issues.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    attestation_path = tmp_path / "attestation.v3.json"
    generate_snapshot_attestation(manifest, attestation_path)
    metadata = {
        "snapshot_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "repo_commit": "b" * 40,
    }

    verified = validate_snapshot_attestation(attestation_path, metadata, metadata)
    assert verified["schema_version"] == "3.0.0"
    assert set(verified["artifacts"]) == {
        "manifest.json", "code_files.json", "code_entities.json",
        "code_relations.json", "frontend_diagnostics.json", "scan_issues.json",
    }
    (tmp_path / "code_relations.json").write_text('[{"tampered":true}]', encoding="utf-8")
    with pytest.raises(ValueError, match="code_relations.json.*SHA"):
        validate_snapshot_attestation(attestation_path, metadata, metadata)


def test_source_only_diagnostics_use_nonindexed_gold_components() -> None:
    from compute_stage2b_metrics import compute_metrics

    sample = case("q1")
    sample["gold_entities"].append({"stable_entity_key": "source-e", "file_path": "source.java", "relevance": "must_recall", "indexed_in_system": False})
    sample["gold_nodes"].append({"stable_entity_key": "source-n", "indexed_in_system": False})
    sample["gold_edges"].append({"source_key": "source-n", "target_key": "source-e", "relation_type": "CALLS_METHOD", "indexed_in_system": False})
    raw = [{
        **retrieval_record("q1", "B4"),
        "hits": [{"stable_entity_key": "source-e", "file_path": "source.java"}],
        "graph_nodes": [{"stable_entity_key": "source-n"}],
        "graph_edges": [{"source_stable_entity_key": "source-n", "target_stable_entity_key": "source-e", "relation_type": "CALLS_METHOD"}],
    }]

    source_only = compute_metrics([sample], raw, [], {}, strict=False)["diagnostics"]["source_only"]

    assert source_only["entity"]["count"] == 1
    assert source_only["nodes"]["question_ids"] == ["q1"]
    assert source_only["edges"]["excluded_from_main"] is True
    assert source_only["entity"]["variants"]["B4"]["status"] == "observed"
    assert source_only["nodes"]["variants"]["B4"]["observed_count"] == 1
