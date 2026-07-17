from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


RUNNERS_DIR = Path(__file__).resolve().parents[2] / "runners"
if str(RUNNERS_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNERS_DIR))

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


IDENTITY = {
    "run_id": "agent-run",
    "dataset_sha256": "a" * 64,
    "repo_commit": "b" * 40,
    "db_sha256": "c" * 64,
    "snapshot_sha256": "d" * 64,
    "config_fingerprint": "e" * 64,
}


def _cases() -> list[dict[str, object]]:
    task_types = ("CODE_QA", "TRACE_CHAIN", "CHANGE_PLAN")
    cases = []
    for index in range(18):
        cases.append(
            {
                "question_id": f"q{index:02d}",
                "question": f"question {index}",
                "expected_task_type": task_types[index % 3],
                "task_type": task_types[index % 3],
                "language": "zh" if index % 2 == 0 else "en",
                "difficulty": ("easy", "medium", "hard")[index % 3],
                "source_answerable": index not in {5, 10, 15},
                "system_answerable": "insufficient" if index in {5, 10, 15} else "full",
            }
        )
    return cases


def test_stability_subset_is_exact_deterministic_stratified_and_prefers_hard() -> None:
    from stage2b_agent import select_stability_subset

    first = select_stability_subset(_cases())
    second = select_stability_subset(list(reversed(_cases())))

    assert [case["question_id"] for case in first] == [case["question_id"] for case in second]
    assert len(first) == 8
    assert {case["expected_task_type"] for case in first} == {
        "CODE_QA", "TRACE_CHAIN", "CHANGE_PLAN"
    }
    assert {case["language"] for case in first} == {"zh", "en"}
    assert {case["source_answerable"] for case in first} == {True, False}
    assert {case["system_answerable"] != "insufficient" for case in first} == {True, False}
    assert sum(case["difficulty"] == "hard" for case in first) >= 3


class FakeCounters:
    def __init__(self, calls: int = 0) -> None:
        self.calls = calls


class FakePlanner:
    def __init__(self, planned: str = "TRACE_CHAIN") -> None:
        self.planned = planned
        self.questions: list[str] = []

    def plan(self, question: str) -> str:
        self.questions.append(question)
        return self.planned


class FakeExecutor:
    def __init__(self, result=None, error: Exception | None = None, counters=None, recorder=None) -> None:
        self.result = result
        self.error = error
        self.counters = counters
        self.recorder = recorder
        self.calls: list[dict[str, object]] = []

    def execute(self, task_type, **kwargs):
        self.calls.append({"task_type": task_type, **kwargs})
        if self.counters is not None:
            self.counters.calls += 2
        if self.recorder is not None:
            self.recorder.add("first raw", 11)
            self.recorder.add("repair raw", 7)
        if self.error:
            raise self.error
        return self.result


class FakeRewriter:
    def details(self, query: str):
        return {
            "original_query": query,
            "effective_query": f"rewritten:{query}",
            "rewrite_degraded": False,
            "rewrite_error": None,
            "rewrite_latency_seconds": 0.1,
        }


class FakeResponseRecorder:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    @property
    def event_count(self) -> int:
        return len(self.events)

    def add(self, content: str, total_tokens: int) -> None:
        ordinal = len(self.events) + 1
        self.events.append({
            "call_ordinal": ordinal,
            "attempt_id": f"attempt-{ordinal}",
            "phase": "initial" if ordinal % 2 == 1 else "repair",
            "call_timestamp": f"2026-01-01T00:00:0{ordinal}+00:00",
            "requested_model": "requested",
            "returned_model": "returned-v1",
            "returned_model_version": "returned-v1",
            "response_id": f"r{ordinal}",
            "response_created": 123,
            "finish_reason": "stop",
            "usage_available": True,
            "prompt_tokens": total_tokens - 2,
            "completion_tokens": 2,
            "total_tokens": total_tokens,
            "raw_assistant_content": content,
            "error": None,
        })

    def slice(self, start_exclusive: int, end_inclusive: int):
        return [dict(event) for event in self.events[start_exclusive:end_inclusive]]

    def begin_case(self) -> None:
        pass

    def end_case(self) -> None:
        pass


def _result(answer: str = "Supported [1]"):
    from app.agent.types import AgentResult, TaskType
    from app.schemas.agent import ContextReferenceRead
    from app.schemas.graph import GraphEdgeRead, GraphNodeRead

    return AgentResult(
        task_type=TaskType.TRACE_CHAIN,
        answer=answer,
        references=(ContextReferenceRead(citation=1, entity_id=1, file_path="src/A.java", start_line=2, end_line=5, entity_type="java_method", qualified_name="A.m"),),
        graph_nodes=(GraphNodeRead(entity_id=1, label="m", entity_type="java_method", qualified_name="A.m", file_path="src/A.java", start_line=2, end_line=5, content="code", metadata={}),),
        graph_edges=(GraphEdgeRead(relation_id=9, source_id=1, target_id=2, relation_type="CALLS_METHOD", confidence=1.0, metadata={}),),
        uncertainties=(),
    )


def _runtime(*, result=None, error=None, planned="TRACE_CHAIN"):
    from stage2b_agent import AgentRuntime

    counters = FakeCounters()
    embedding_counters = FakeCounters(3)
    rewrite_counters = FakeCounters(4)
    recorder = FakeResponseRecorder()
    executor = FakeExecutor(result=result or _result(), error=error, counters=counters, recorder=recorder)
    return AgentRuntime(
        project_id=7,
        entity_keys={1: "stable-1", 2: "stable-2"},
        planner=FakePlanner(planned),
        executor=executor,
        llm_counters=counters,
        embedding_counters=embedding_counters,
        rewrite_counters=rewrite_counters,
        response_recorder=recorder,
        rewriter=FakeRewriter(),
        identity=IDENTITY,
    )


def test_evaluate_captures_planner_route_serializes_stable_graph_and_call_delta() -> None:
    from stage2b_agent import evaluate_agent_case

    runtime = _runtime()
    record = evaluate_agent_case(
        {"question_id": "q1", "question": "trace this", "expected_task_type": "TRACE_CHAIN"},
        "B5",
        0,
        runtime,
    )

    assert runtime.planner.questions == ["trace this"]
    assert runtime.executor.calls[0]["task_type"] == "TRACE_CHAIN"
    assert record["planned_task_type"] == "TRACE_CHAIN"
    assert record["expected_task_type"] == "TRACE_CHAIN"
    assert record["provider_llm_call_delta"] == 2
    assert record["provider_call_deltas"] == {
        "agent_llm": 2,
        "query_embedding": 0,
        "rewrite_llm": 0,
    }
    assert record["repair_attempted_inferred"] is True
    assert [event["raw_assistant_content"] for event in record["llm_response_events"]] == [
        "first raw", "repair raw"
    ]
    assert [event["phase"] for event in record["llm_response_events"]] == ["initial", "repair"]
    assert record["repair_attempted_inferred"] is True
    assert record["repair_succeeded"] is True
    assert record["repair_failed"] is False
    assert record["references"][0]["stable_entity_key"] == "stable-1"
    assert record["graph_nodes"][0]["stable_entity_key"] == "stable-1"
    assert record["graph_edges"][0]["source_stable_entity_key"] == "stable-1"
    assert record["citation_validation"] == {"is_valid": True, "invalid_citations": [], "invalid_paths": []}
    assert all(record[key] == value for key, value in IDENTITY.items())


def test_repair_is_failed_when_final_answer_is_guard_fallback() -> None:
    from app.services.evidence_validator import EVIDENCE_VALIDATION_FAILED_ANSWER
    from stage2b_agent import evaluate_agent_case

    fallback = _result(EVIDENCE_VALIDATION_FAILED_ANSWER)
    fallback = type(fallback)(
        task_type=fallback.task_type,
        answer=fallback.answer,
        references=fallback.references,
        graph_nodes=fallback.graph_nodes,
        graph_edges=fallback.graph_edges,
        uncertainties=("Evidence validation repair limit reached.",),
    )
    record = evaluate_agent_case(
        {"question_id": "q1", "question": "trace", "expected_task_type": "TRACE_CHAIN"},
        "B5", 0, _runtime(result=fallback),
    )

    assert record["repair_attempted_inferred"] is True
    assert record["final_evidence_validation_passed"] is False
    assert record["repair_succeeded"] is False
    assert record["repair_failed"] is True


def test_exception_is_retained_with_identity_and_provider_delta() -> None:
    from stage2b_agent import evaluate_agent_case

    record = evaluate_agent_case(
        {"question_id": "q1", "question": "trace", "expected_task_type": "TRACE_CHAIN"},
        "B5", 0, _runtime(error=RuntimeError("provider exploded")),
    )

    assert record["status"] == "error"
    assert record["error"] == {"type": "RuntimeError", "message": "provider exploded"}
    assert record["provider_llm_call_delta"] == 2
    assert record["answer"] == ""
    assert record["references"] == []


def test_agent_raw_error_redacts_credentials() -> None:
    from stage2b_agent import evaluate_agent_case

    message = (
        "Bearer bearer-secret api_key=key-secret "
        "https://user:pass@example.test/v1?token=url-secret"
    )
    record = evaluate_agent_case(
        {"question_id": "q1", "question": "trace", "expected_task_type": "TRACE_CHAIN"},
        "B5", 0, _runtime(error=RuntimeError(message)),
    )
    encoded = json.dumps(record)
    assert "bearer-secret" not in encoded
    assert "key-secret" not in encoded
    assert "url-secret" not in encoded
    assert "user:pass" not in encoded
    assert "[REDACTED]" in encoded


def test_resume_identity_and_ledger_counts_fail_closed(tmp_path: Path) -> None:
    from stage2b_agent import validate_resume_state

    path = tmp_path / "agent.jsonl"
    record = {
        **IDENTITY,
        "question_id": "q1",
        "variant": "B5",
        "run_index": 0,
        "provider_llm_call_delta": 1,
        "provider_call_deltas": {"agent_llm": 1, "query_embedding": 2, "rewrite_llm": 0},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    expected = {("q1", "B5", 0), ("q2", "B5", 0)}
    ledgers = {"agent_llm": 1, "query_embedding": 2, "rewrite_llm": 0}
    state = validate_resume_state(path, IDENTITY, ledger_calls=ledgers, expected_keys=expected)
    assert state.records == 1
    assert state.orphan_calls == {"agent_llm": 0, "query_embedding": 0, "rewrite_llm": 0}

    with pytest.raises(ValueError, match="identity mismatch"):
        validate_resume_state(path, {**IDENTITY, "db_sha256": "x" * 64}, ledger_calls=ledgers, expected_keys=expected)
    orphan = validate_resume_state(path, IDENTITY, ledger_calls={**ledgers, "agent_llm": 2}, expected_keys=expected)
    assert orphan.orphan_calls["agent_llm"] == 1
    with pytest.raises(ValueError, match="raw records account"):
        validate_resume_state(path, IDENTITY, ledger_calls={**ledgers, "agent_llm": 0}, expected_keys=expected)
    with pytest.raises(ValueError, match="incomplete"):
        validate_resume_state(path, IDENTITY, ledger_calls=ledgers, expected_keys=expected, require_complete=True)


def test_resume_rejects_duplicate_and_out_of_schedule_keys(tmp_path: Path) -> None:
    from stage2b_agent import validate_resume_state

    path = tmp_path / "agent.jsonl"
    record = {
        **IDENTITY,
        "question_id": "q1",
        "variant": "B5",
        "run_index": 0,
        "provider_llm_call_delta": 0,
        "provider_call_deltas": {"agent_llm": 0, "query_embedding": 0, "rewrite_llm": 0},
    }
    path.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        validate_resume_state(path, IDENTITY, ledger_calls={"agent_llm": 0, "query_embedding": 0, "rewrite_llm": 0}, expected_keys={("q1", "B5", 0)})

    record["variant"] = "A9"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside expected schedule"):
        validate_resume_state(path, IDENTITY, ledger_calls={"agent_llm": 0, "query_embedding": 0, "rewrite_llm": 0}, expected_keys={("q1", "B5", 0)})


def test_ablation_status_marks_a7_and_a9_not_executable_atomically(tmp_path: Path) -> None:
    from stage2b_agent import write_ablation_status

    path = tmp_path / "status.json"
    write_ablation_status(path, IDENTITY)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["A7"]["status"] == "not_executable"
    assert "multi-turn" in payload["A7"]["reason"]
    assert payload["A9"]["status"] == "not_executable"
    assert "validate-but-no-repair" in payload["A9"]["reason"]
    assert payload["A8"]["status"] == "executable"
    assert all(payload["identity"][key] == value for key, value in IDENTITY.items())
    assert not (tmp_path / ".status.json.tmp").exists()


def test_a8_always_valid_validator_removes_guard_without_changing_post_validation() -> None:
    from app.schemas.agent import ContextReferenceRead
    from stage2b_agent import AlwaysValidEvidenceValidator

    reference = ContextReferenceRead(citation=1, entity_id=1, file_path="src/A.java", start_line=1, end_line=2, entity_type="java_method", qualified_name="A.m")
    validation = AlwaysValidEvidenceValidator().validate("unsupported [99] src/Z.java", [reference])

    assert validation.is_valid is True
    assert validation.invalid_citations == ()
    assert validation.invalid_paths == ()


def test_run_schedule_has_b5_full_plus_two_subset_runs_and_separate_a8() -> None:
    from stage2b_agent import build_run_schedule

    cases = _cases()
    schedule = build_run_schedule(cases)

    assert len([item for item in schedule if item[0] == "B5" and item[1] == 0]) == 18
    assert len([item for item in schedule if item[0] == "B5" and item[1] == 1]) == 8
    assert len([item for item in schedule if item[0] == "B5" and item[1] == 2]) == 8
    assert len([item for item in schedule if item[0] == "A8" and item[1] == 0]) == 18
    assert not any(item[0] == "A8" and item[1] != 0 for item in schedule)


def test_evaluation_does_not_write_conversations() -> None:
    from stage2b_agent import evaluate_agent_case

    runtime = _runtime()
    evaluate_agent_case(
        {"question_id": "q", "question": "trace", "expected_task_type": "TRACE_CHAIN"},
        "B5", 0, runtime,
    )

    assert not hasattr(runtime, "conversations")
    assert runtime.executor.calls[0]["conversation_memory"] == ""


def test_index_provenance_mismatch_fails_before_execution() -> None:
    from stage2b_agent import require_verified_retrieval_provenance

    metadata = {
        "dataset_sha256": IDENTITY["dataset_sha256"],
        "repo_commit": IDENTITY["repo_commit"],
        "db_sha256": IDENTITY["db_sha256"],
        "snapshot_sha256": IDENTITY["snapshot_sha256"],
        "build": {"status": "completed", "db_sha256": "wrong"},
    }
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        require_verified_retrieval_provenance(metadata, IDENTITY)


def test_current_retrieval_config_change_refuses_reuse(tmp_path: Path) -> None:
    from stage2b_agent import require_current_retrieval_config
    from stage2b_retrieval import config_fingerprint, retrieval_config

    args = SimpleNamespace(qdrant_path=tmp_path / "qdrant")
    settings = SimpleNamespace(
        embedding_provider="api", embedding_model="embedding-3",
        embedding_dimensions=1024, embedding_base_url="https://embed.example/v1",
        llm_model="model", llm_base_url="https://llm.example/v1",
        chunk_max_content_chars=4000,
    )
    config = retrieval_config(settings, args)
    metadata = {"effective_config": config, "config_fingerprint": config_fingerprint(config)}
    require_current_retrieval_config(metadata, settings, args)

    changed_model = SimpleNamespace(**{**settings.__dict__, "embedding_model": "other-same-dimension"})
    with pytest.raises(RuntimeError, match="current retrieval config"):
        require_current_retrieval_config(metadata, changed_model, args)
    with pytest.raises(RuntimeError, match="current retrieval config"):
        require_current_retrieval_config(metadata, settings, SimpleNamespace(qdrant_path=tmp_path / "other"))


def test_real_db_reference_node_and_edge_serialize_canonical_gold_keys() -> None:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.models import CodeEntity, CodeRelation
    from app.schemas.agent import ContextReferenceRead
    from app.schemas.graph import GraphEdgeRead, GraphNodeRead
    from stage2b_agent import _serialize_edge, _serialize_node, _serialize_reference
    from stage2b_retrieval import build_canonical_entity_keys

    root = Path(__file__).resolve().parents[3]
    dataset = [json.loads(line) for line in (root / "evaluation/datasets/pilot-current.jsonl").read_text(encoding="utf-8").splitlines()]
    gold = dataset[0]["gold_entities"][0]
    graph_case = next(case for case in dataset if case["gold_edges"])
    gold_edge = next(edge for edge in graph_case["gold_edges"] if edge["indexed_in_system"])
    engine = create_engine(f"sqlite+pysqlite:///{(root / 'evaluation/runtime/pilot/rca_eval.db').as_posix()}")
    with Session(engine) as session:
        rows = session.scalars(select(CodeEntity).order_by(CodeEntity.id)).all()
        keys = build_canonical_entity_keys(rows, dataset[0]["repo_id"], dataset[0]["commit_sha"])
        ids_by_key = {key: runtime_id for runtime_id, key in keys.items()}
        row = session.scalar(select(CodeEntity).where(
            CodeEntity.file_path == gold["file_path"],
            CodeEntity.qualified_name == gold["qualified_name"],
            CodeEntity.start_line == gold["start_line"],
            CodeEntity.end_line == gold["end_line"],
        ))
        assert row is not None
        relation = session.scalar(select(CodeRelation).where(
            CodeRelation.source_id == ids_by_key[gold_edge["source_key"]],
            CodeRelation.target_id == ids_by_key[gold_edge["target_key"]],
            CodeRelation.relation_type == gold_edge["relation_type"],
        ))
        assert relation is not None
    reference = ContextReferenceRead(
        citation=1, entity_id=row.id, file_path=row.file_path, start_line=row.start_line,
        end_line=row.end_line, entity_type=row.entity_type, qualified_name=row.qualified_name,
    )
    serialized = _serialize_reference(reference, keys)
    assert serialized["stable_entity_key"] == gold["stable_entity_key"]
    assert len(serialized["stable_entity_key"]) == 64
    source = next(item for item in rows if item.id == relation.source_id)
    node = GraphNodeRead(
        entity_id=source.id, label=source.name, entity_type=source.entity_type,
        qualified_name=source.qualified_name, file_path=source.file_path,
        start_line=source.start_line, end_line=source.end_line,
        content=source.content, metadata={},
    )
    serialized_node = _serialize_node(node, keys)
    assert serialized_node["stable_entity_key"] == gold_edge["source_key"]
    serialized_edge = _serialize_edge(GraphEdgeRead(
        relation_id=relation.id, source_id=relation.source_id,
        target_id=relation.target_id, relation_type=relation.relation_type,
        confidence=relation.confidence, metadata={},
    ), keys)
    assert serialized_edge["source_stable_entity_key"] == gold_edge["source_key"]
    assert serialized_edge["target_stable_entity_key"] == gold_edge["target_key"]
    assert all(len(serialized_edge[key]) == 64 for key in (
        "source_stable_entity_key", "target_stable_entity_key"
    ))


def test_durable_response_recorder_captures_success_failure_usage_and_replays(tmp_path: Path) -> None:
    from stage2b_agent import DurableLlmResponseRecorder, ResponseRecordingOpenAIClient
    from stage2b_retrieval import DurableCallCounters

    class Endpoint:
        def __init__(self) -> None:
            self.fail = False

        def create(self, **request):
            if self.fail:
                raise RuntimeError("auth failed")
            usage = SimpleNamespace(prompt_tokens=8, completion_tokens=3, total_tokens=11)
            message = SimpleNamespace(content="raw assistant")
            choice = SimpleNamespace(message=message, finish_reason="stop")
            return SimpleNamespace(
                id="resp-1", created=1234, model="provider-model-2026-07",
                system_fingerprint="fp-1", usage=usage, choices=[choice],
            )

    endpoint = Endpoint()
    raw = SimpleNamespace(chat=SimpleNamespace(completions=endpoint))
    counters = DurableCallCounters(tmp_path / "calls.jsonl")
    recorder = DurableLlmResponseRecorder(tmp_path / "responses.jsonl")
    client = ResponseRecordingOpenAIClient(raw, recorder, counters)

    recorder.begin_case()
    response = client.chat.completions.create(model="requested-model", messages=[{"role": "user", "content": "SECRET PROMPT"}])
    assert response.id == "resp-1"
    endpoint.fail = True
    with pytest.raises(RuntimeError, match="auth failed"):
        client.chat.completions.create(model="requested-model", messages=[])
    recorder.end_case()

    replayed = DurableLlmResponseRecorder(tmp_path / "responses.jsonl")
    assert [event["call_ordinal"] for event in replayed.slice(0, 2)] == [1, 2]
    success, failure = replayed.slice(0, 2)
    assert success["requested_model"] == "requested-model"
    assert success["returned_model"] == "provider-model-2026-07"
    assert success["finish_reason"] == "stop"
    assert success["total_tokens"] == 11
    assert success["raw_assistant_content"] == "raw assistant"
    assert "+00:00" in success["call_timestamp"]
    assert failure["error"] == {"type": "RuntimeError", "message": "auth failed"}
    assert success["attempt_id"] != failure["attempt_id"]
    assert [success["phase"], failure["phase"]] == ["initial", "repair"]
    call_events = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    started_ids = [event["attempt_id"] for event in call_events if event["event"] == "started"]
    assert started_ids == [success["attempt_id"], failure["attempt_id"]]
    encoded = (tmp_path / "responses.jsonl").read_text(encoding="utf-8")
    assert "SECRET PROMPT" not in encoded
    replayed.validate_against(counters)


def test_response_recorder_allows_pending_started_attempt(tmp_path: Path) -> None:
    from stage2b_agent import DurableLlmResponseRecorder
    from stage2b_retrieval import DurableCallCounters

    counters = DurableCallCounters(tmp_path / "calls.jsonl")
    attempt_id = counters.begin_attempt()
    recorder = DurableLlmResponseRecorder(tmp_path / "responses.jsonl")
    with pytest.raises(RuntimeError, match="pending provider attempt"):
        recorder.reconcile_pending(counters)
    assert counters.pending == 1

    recorder.append({
        "attempt_id": attempt_id, "phase": "initial",
        "call_timestamp": "2026-01-01T00:00:00+00:00",
        "requested_model": "m", "returned_model": "m", "returned_model_version": "m",
        "response_id": "r", "response_created": 1, "finish_reason": "stop",
        "usage_available": False, "prompt_tokens": None, "completion_tokens": None,
        "total_tokens": None, "raw_assistant_content": "done", "error": None,
        "provider_latency_seconds": 0.25,
    })
    recorder.reconcile_pending(counters)
    assert counters.pending == 0
    assert counters.successes == 1
    recorder.validate_against(counters)

    from stage2b_agent import ResumeState, require_no_orphan_provider_calls
    with pytest.raises(RuntimeError, match="orphan provider calls"):
        require_no_orphan_provider_calls(ResumeState(
            records=0,
            orphan_calls={"agent_llm": 1, "query_embedding": 0, "rewrite_llm": 0},
        ))


def test_unconfirmed_embedding_or_rewrite_attempt_fails_closed() -> None:
    from stage2b_agent import require_no_unconfirmed_provider_calls

    counters = {
        "agent_llm": SimpleNamespace(pending=0),
        "query_embedding": SimpleNamespace(pending=1),
        "rewrite_llm": SimpleNamespace(pending=0),
    }
    with pytest.raises(RuntimeError, match="query_embedding"):
        require_no_unconfirmed_provider_calls(counters)


def test_response_error_sanitizes_bearer_api_key_and_url_credentials(tmp_path: Path) -> None:
    from stage2b_agent import DurableLlmResponseRecorder, ResponseRecordingOpenAIClient
    from stage2b_retrieval import DurableCallCounters

    message = (
        "Bearer very-secret api_key=also-secret "
        "https://user:pass@example.test/v1?api_key=url-secret"
    )
    endpoint = SimpleNamespace(create=lambda **request: (_ for _ in ()).throw(RuntimeError(message)))
    raw = SimpleNamespace(chat=SimpleNamespace(completions=endpoint))
    counters = DurableCallCounters(tmp_path / "calls.jsonl")
    recorder = DurableLlmResponseRecorder(tmp_path / "responses.jsonl")
    client = ResponseRecordingOpenAIClient(raw, recorder, counters)
    recorder.begin_case()
    with pytest.raises(RuntimeError):
        client.chat.completions.create(model="m", messages=[])
    encoded = (tmp_path / "responses.jsonl").read_text(encoding="utf-8")
    assert "very-secret" not in encoded
    assert "also-secret" not in encoded
    assert "url-secret" not in encoded
    assert "user:pass" not in encoded
    assert "[REDACTED]" in encoded


def test_agent_smoke_failure_preserves_failure_and_does_not_poison_canonical(tmp_path: Path) -> None:
    from stage2b_agent import run_agent_smoke_gate

    canonical = tmp_path / "canonical.jsonl"
    canonical.write_bytes(b"canonical unchanged\n")
    runtime = _runtime(error=RuntimeError("schema failure"))
    schedule = [
        ("B5", 0, {"question_id": "q1", "question": "one", "expected_task_type": "TRACE_CHAIN"}),
        ("B5", 0, {"question_id": "q2", "question": "two", "expected_task_type": "TRACE_CHAIN"}),
    ]

    with pytest.raises(RuntimeError, match="smoke agent failed"):
        run_agent_smoke_gate(schedule, runtime, canonical)

    assert canonical.read_bytes() == b"canonical unchanged\n"
    failures = list(tmp_path.glob("canonical.smoke-failed-*.jsonl"))
    assert len(failures) == 1
    records = [json.loads(line) for line in failures[0].read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert all(record["status"] == "error" for record in records)


def test_agent_smoke_promotes_both_only_after_success(tmp_path: Path) -> None:
    from stage2b_agent import run_agent_smoke_gate, run_schedule

    canonical = tmp_path / "canonical.jsonl"
    runtime = _runtime()
    schedule = [
        ("B5", 0, {"question_id": "q1", "question": "one", "expected_task_type": "TRACE_CHAIN"}),
        ("B5", 0, {"question_id": "q2", "question": "two", "expected_task_type": "TRACE_CHAIN"}),
    ]

    promoted = run_agent_smoke_gate(schedule, runtime, canonical)
    calls_after_smoke = runtime.llm_counters.calls

    assert len(promoted) == 2
    assert len(canonical.read_text(encoding="utf-8").splitlines()) == 2
    assert run_schedule(schedule, runtime, canonical) == 0
    assert runtime.llm_counters.calls == calls_after_smoke


def test_llm_reproducibility_metadata_reports_models_usage_and_resume_start() -> None:
    from stage2b_agent import llm_reproducibility_metadata

    recorder = FakeResponseRecorder()
    recorder.add("one", 11)
    recorder.add("two", 7)
    metadata = llm_reproducibility_metadata(
        recorder,
        requested_model="requested",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T01:00:00+00:00",
    )

    assert metadata["started_at"] == "2026-01-01T00:00:00+00:00"
    assert metadata["finished_at"] == "2026-01-01T01:00:00+00:00"
    assert metadata["temperature"] == 0
    assert metadata["seed"] == "not_requested/provider_support_unknown"
    assert metadata["requested_model"] == "requested"
    assert metadata["returned_model_versions_observed"] == ["returned-v1"]
    assert metadata["usage_totals"]["total_tokens"] == 18
    assert metadata["raw_response_capture_enabled"] is True
