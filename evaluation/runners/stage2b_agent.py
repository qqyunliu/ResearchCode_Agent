"""Stage 2B real-service Agent benchmark runner.

This composes the same deterministic planner and task services as the product
API, but invokes ``AgentExecutor`` directly.  Canonical cases are single-turn,
so conversation rows are deliberately neither created nor mutated.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from stage2b_common import (  # noqa: E402
    JsonlCheckpointWriter,
    checkpoint_key,
    sanitize_error_message,
    sha256_file,
    verify_sha256,
)
from stage2b_retrieval import (  # noqa: E402
    DurableCallCounters,
    config_fingerprint,
    count_validated_records,
    load_dataset,
    resolve_run_id,
    sanitize_provider_metadata,
    verify_reusable_index,
    write_metadata,
)


LIMIT = 10
RAW_IDENTITY_FIELDS = (
    "run_id",
    "dataset_sha256",
    "repo_commit",
    "db_sha256",
    "snapshot_sha256",
    "config_fingerprint",
)


class AlwaysValidEvidenceValidator:
    """A8 switch: preserve generation but bypass validation and repair."""

    def validate(self, answer: str, references: Sequence[Any]) -> Any:
        from app.services.evidence_validator import AnswerEvidenceValidationResult

        return AnswerEvidenceValidationResult()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attribute(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class DurableLlmResponseRecorder:
    """Append-only SDK response evidence with stable replay ordinals."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict[str, Any]] = []
        self._active_case_calls: int | None = None
        seen_attempts: set[str] = set()
        if self.path.exists():
            content = self.path.read_bytes()
            lines = content.splitlines(keepends=True)
            torn = bool(content) and not content.endswith((b"\n", b"\r"))
            for index, raw in enumerate(lines):
                payload = raw.rstrip(b"\r\n")
                if not payload.strip():
                    continue
                try:
                    event = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    if torn and index == len(lines) - 1:
                        Path(f"{self.path}.torn").write_bytes(payload)
                        valid = b"".join(lines[:-1])
                        with self.path.open("r+b") as stream:
                            stream.seek(len(valid))
                            stream.truncate()
                            stream.flush()
                            os.fsync(stream.fileno())
                        break
                    raise ValueError(
                        f"invalid LLM response ledger at {self.path}:{index + 1}"
                    ) from error
                ordinal = event.get("call_ordinal") if isinstance(event, Mapping) else None
                if ordinal != len(self.events) + 1:
                    raise ValueError(
                        f"invalid LLM response ordinal at {self.path}:{index + 1}"
                    )
                attempt_id = str(event.get("attempt_id", ""))
                if not attempt_id or attempt_id in seen_attempts:
                    raise ValueError(
                        f"invalid or duplicate LLM attempt id at {self.path}:{index + 1}"
                    )
                if event.get("phase") not in {"initial", "repair"}:
                    raise ValueError(f"invalid LLM phase at {self.path}:{index + 1}")
                seen_attempts.add(attempt_id)
                self.events.append(dict(event))

    @property
    def event_count(self) -> int:
        return len(self.events)

    def append(self, event: Mapping[str, Any]) -> dict[str, Any]:
        payload = {"call_ordinal": self.event_count + 1, **dict(event)}
        attempt_id = str(payload.get("attempt_id", ""))
        if not attempt_id or any(item.get("attempt_id") == attempt_id for item in self.events):
            raise ValueError("LLM response event requires a unique attempt_id")
        if payload.get("phase") not in {"initial", "repair"}:
            raise ValueError("LLM response event requires phase initial or repair")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(payload)
        return dict(payload)

    def slice(self, start_exclusive: int, end_inclusive: int) -> list[dict[str, Any]]:
        if start_exclusive < 0 or end_inclusive < start_exclusive or end_inclusive > self.event_count:
            raise ValueError("invalid LLM response ordinal slice")
        return [dict(event) for event in self.events[start_exclusive:end_inclusive]]

    def begin_case(self) -> None:
        if self._active_case_calls is not None:
            raise RuntimeError("an LLM response case is already active")
        self._active_case_calls = 0

    def claim_phase(self) -> str:
        if self._active_case_calls is None:
            raise RuntimeError("LLM response phase requested outside an active case")
        phase = "initial" if self._active_case_calls == 0 else "repair"
        self._active_case_calls += 1
        return phase

    def end_case(self) -> None:
        if self._active_case_calls is None:
            raise RuntimeError("no LLM response case is active")
        self._active_case_calls = None

    @staticmethod
    def _attempt_states(counters: Any) -> dict[str, str | None]:
        states: dict[str, str | None] = {}
        if not counters.path.exists():
            return states
        for line_number, line in enumerate(
            counters.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            event = json.loads(line)
            event_type = event.get("event")
            if event_type == "started":
                attempt_id = str(event["attempt_id"])
                if attempt_id in states:
                    raise ValueError(f"duplicate call-ledger attempt at line {line_number}")
                states[attempt_id] = None
            elif event_type == "finished":
                attempt_id = str(event["attempt_id"])
                if attempt_id not in states or states[attempt_id] is not None:
                    raise ValueError(f"invalid call-ledger finish at line {line_number}")
                states[attempt_id] = str(event["outcome"])
            else:
                raise ValueError(
                    "legacy call-ledger events cannot be reconciled with response attempt IDs"
                )
        return states

    def reconcile_pending(self, counters: Any) -> None:
        states = self._attempt_states(counters)
        by_attempt = {str(event["attempt_id"]): event for event in self.events}
        unresolved = [attempt_id for attempt_id, outcome in states.items() if outcome is None]
        for attempt_id in unresolved:
            response = by_attempt.get(attempt_id)
            if response is None:
                raise RuntimeError(
                    f"pending provider attempt {attempt_id} has no durable response; refusing to resend"
                )
            outcome = "failure" if response.get("error") else "success"
            counters.finish_attempt(
                attempt_id,
                outcome,
                float(response.get("provider_latency_seconds", 0.0)),
            )
        self.validate_against(counters)

    def validate_against(self, counters: Any) -> None:
        states = self._attempt_states(counters)
        by_attempt = {str(event["attempt_id"]): event for event in self.events}
        if set(by_attempt) - set(states):
            raise ValueError("LLM response references an unknown call-ledger attempt")
        for attempt_id, outcome in states.items():
            response = by_attempt.get(attempt_id)
            if outcome is None:
                continue
            if response is None:
                raise ValueError("terminal call-ledger attempt lacks a durable response event")
            response_outcome = "failure" if response.get("error") else "success"
            if response_outcome != outcome:
                raise ValueError("LLM response outcome disagrees with call-ledger finish")


class _ResponseRecordingCompletions:
    def __init__(self, delegate: Any, recorder: DurableLlmResponseRecorder, counters: Any) -> None:
        self.delegate = delegate
        self.recorder = recorder
        self.counters = counters

    def create(self, **request: Any) -> Any:
        phase = self.recorder.claim_phase()
        attempt_id = self.counters.begin_attempt()
        started = time.perf_counter()
        requested_model = request.get("model")
        timestamp = _utc_now()
        try:
            response = self.delegate.create(**request)
        except Exception as error:
            latency = time.perf_counter() - started
            self.recorder.append({
                "attempt_id": attempt_id,
                "phase": phase,
                "call_timestamp": timestamp,
                "requested_model": requested_model,
                "returned_model": None,
                "returned_model_version": None,
                "response_id": None,
                "response_created": None,
                "finish_reason": None,
                "usage_available": False,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "raw_assistant_content": None,
                "provider_latency_seconds": latency,
                "error": {
                    "type": type(error).__name__,
                    "message": sanitize_error_message(error),
                },
            })
            self.counters.finish_attempt(attempt_id, "failure", latency)
            raise
        choices = _attribute(response, "choices", ()) or ()
        first_choice = choices[0] if choices else None
        message = _attribute(first_choice, "message")
        usage = _attribute(response, "usage")
        usage_values = {
            name: _attribute(usage, name) if usage is not None else None
            for name in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        returned_model = _attribute(response, "model")
        latency = time.perf_counter() - started
        self.recorder.append({
            "attempt_id": attempt_id,
            "phase": phase,
            "call_timestamp": timestamp,
            "requested_model": requested_model,
            "returned_model": returned_model,
            "returned_model_version": returned_model,
            "system_fingerprint": _attribute(response, "system_fingerprint"),
            "response_id": _attribute(response, "id"),
            "response_created": _attribute(response, "created"),
            "finish_reason": _attribute(first_choice, "finish_reason"),
            "usage_available": usage is not None and any(value is not None for value in usage_values.values()),
            **usage_values,
            "raw_assistant_content": _attribute(message, "content"),
            "provider_latency_seconds": latency,
            "error": None,
        })
        self.counters.finish_attempt(attempt_id, "success", latency)
        return response


class _ResponseRecordingChat:
    def __init__(self, delegate: Any, recorder: DurableLlmResponseRecorder, counters: Any) -> None:
        self.delegate = delegate
        self.completions = _ResponseRecordingCompletions(
            delegate.completions, recorder, counters
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


class ResponseRecordingOpenAIClient:
    """OpenAI client proxy capturing responses without persisting prompts."""

    def __init__(self, delegate: Any, recorder: DurableLlmResponseRecorder, counters: Any) -> None:
        self.delegate = delegate
        self.chat = _ResponseRecordingChat(delegate.chat, recorder, counters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


@dataclass
class AgentRuntime:
    project_id: int
    entity_keys: Mapping[int, str]
    planner: Any
    executor: Any
    llm_counters: Any
    embedding_counters: Any
    rewrite_counters: Any
    response_recorder: Any
    rewriter: Any
    identity: Mapping[str, str]
    a8_executor: Any | None = None

    def executor_for(self, variant: str) -> Any:
        if variant == "B5":
            return self.executor
        if variant == "A8" and self.a8_executor is not None:
            return self.a8_executor
        raise ValueError(f"unsupported or unconfigured agent variant: {variant}")


def _is_answerable(case: Mapping[str, Any]) -> bool:
    value = case.get("source_answerable")
    if type(value) is not bool:
        raise ValueError("stability cases require boolean source_answerable")
    return value


def select_stability_subset(
    cases: Sequence[Mapping[str, Any]],
    size: int = 8,
) -> list[Mapping[str, Any]]:
    """Return a deterministic stratified subset, preferring harder cases."""
    if len(cases) < size:
        raise ValueError(f"stability subset requires at least {size} cases")
    ordered = sorted(cases, key=lambda case: str(case["question_id"]))
    task_values = {str(case.get("expected_task_type", case.get("task_type"))) for case in ordered}
    language_values = {str(case.get("language")) for case in ordered}
    answerability_values = {_is_answerable(case) for case in ordered}
    if len(task_values) < 3 or not {"zh", "en"}.issubset(language_values) or len(answerability_values) < 2:
        raise ValueError("cases cannot satisfy the required stability strata")

    uncovered: set[tuple[str, object]] = {
        *(('task', value) for value in task_values),
        *(('language', value) for value in ("zh", "en")),
        *(('answerable', value) for value in (True, False)),
    }
    difficulty_rank = {"hard": 3, "medium": 2, "easy": 1}
    selected: list[Mapping[str, Any]] = []
    remaining = list(ordered)
    while len(selected) < size:
        def candidate_key(case: Mapping[str, Any]) -> tuple[int, int, int, str]:
            categories = {
                ("task", str(case.get("expected_task_type", case.get("task_type")))),
                ("language", str(case.get("language"))),
                ("answerable", _is_answerable(case)),
            }
            return (
                len(categories & uncovered),
                difficulty_rank.get(str(case.get("difficulty", "easy")), 0),
                int(not _is_answerable(case)),
                str(case["question_id"]),
            )

        chosen = max(remaining, key=candidate_key)
        remaining.remove(chosen)
        selected.append(chosen)
        uncovered -= {
            ("task", str(chosen.get("expected_task_type", chosen.get("task_type")))),
            ("language", str(chosen.get("language"))),
            ("answerable", _is_answerable(chosen)),
        }
    if uncovered:
        raise ValueError(f"stability subset did not cover strata: {sorted(uncovered)!r}")
    return sorted(selected, key=lambda case: str(case["question_id"]))


def build_run_schedule(
    cases: Sequence[Mapping[str, Any]],
) -> list[tuple[str, int, Mapping[str, Any]]]:
    full = sorted(cases, key=lambda case: str(case["question_id"]))
    stability = select_stability_subset(full)
    return list(chain(
        (("B5", 0, case) for case in full),
        (("B5", run_index, case) for run_index in (1, 2) for case in stability),
        (("A8", 0, case) for case in full),
    ))


def schedule_keys(
    schedule: Sequence[tuple[str, int, Mapping[str, Any]]],
) -> set[tuple[str, str, int]]:
    keys = {
        (str(case["question_id"]), variant, run_index)
        for variant, run_index, case in schedule
    }
    if len(keys) != len(schedule):
        raise ValueError("run schedule contains duplicate checkpoint keys")
    return keys


def stability_subset_summary(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    subset = select_stability_subset(cases)
    return {
        "question_ids": [str(case["question_id"]) for case in subset],
        "task_types": sorted({str(case["expected_task_type"]) for case in subset}),
        "languages": sorted({str(case["language"]) for case in subset}),
        "source_answerable": sorted({_is_answerable(case) for case in subset}),
        "system_answerable": sorted({str(case["system_answerable"]) for case in subset}),
        "difficulties": sorted({str(case["difficulty"]) for case in subset}),
    }


def _serialize_reference(reference: Any, entity_keys: Mapping[int, str]) -> dict[str, Any]:
    return {
        **reference.model_dump(mode="json"),
        "runtime_entity_id": reference.entity_id,
        "stable_entity_key": entity_keys.get(reference.entity_id),
    }


def _serialize_node(node: Any, entity_keys: Mapping[int, str]) -> dict[str, Any]:
    payload = node.model_dump(mode="json")
    payload["runtime_entity_id"] = node.entity_id
    payload["stable_entity_key"] = entity_keys.get(node.entity_id)
    payload.pop("content", None)
    return payload


def _serialize_edge(edge: Any, entity_keys: Mapping[int, str]) -> dict[str, Any]:
    payload = edge.model_dump(mode="json")
    payload.update({
        "runtime_relation_id": edge.relation_id,
        "source_runtime_id": edge.source_id,
        "target_runtime_id": edge.target_id,
        "source_stable_entity_key": entity_keys.get(edge.source_id),
        "target_stable_entity_key": entity_keys.get(edge.target_id),
    })
    return payload


def _rewrite_details(rewriter: Any, question: str) -> dict[str, Any]:
    try:
        return dict(rewriter.details(question))
    except (KeyError, AttributeError):
        return {
            "original_query": question,
            "effective_query": question,
            "rewrite_degraded": None,
            "rewrite_error": None,
            "rewrite_latency_seconds": None,
            "observed": False,
        }


def _citation_validation(answer: str, references: Sequence[Any]) -> dict[str, Any]:
    from app.services.evidence_validator import AnswerEvidenceValidator

    validation = AnswerEvidenceValidator().validate(answer, references)
    return {
        "is_valid": validation.is_valid,
        "invalid_citations": list(validation.invalid_citations),
        "invalid_paths": list(validation.invalid_paths),
    }


def evaluate_agent_case(
    case: Mapping[str, Any],
    variant: str,
    run_index: int,
    runtime: AgentRuntime,
) -> dict[str, Any]:
    """Execute one record and retain failures as first-class observations."""
    from app.services.evidence_validator import EVIDENCE_VALIDATION_FAILED_ANSWER

    question = str(case["question"])
    before_calls = {
        "agent_llm": int(runtime.llm_counters.calls),
        "query_embedding": int(runtime.embedding_counters.calls),
        "rewrite_llm": int(runtime.rewrite_counters.calls),
    }
    before_response_ordinal = int(runtime.response_recorder.event_count)
    started = time.perf_counter()
    expected = str(case.get("expected_task_type", case.get("task_type", "")))
    planned = ""
    answer = ""
    references: list[Any] = []
    graph_nodes: list[Any] = []
    graph_edges: list[Any] = []
    uncertainties: list[str] = []
    status = "ok"
    error_record = None
    runtime.response_recorder.begin_case()
    try:
        plan = runtime.planner.plan(question)
        planned = str(getattr(plan, "value", plan))
        result = runtime.executor_for(variant).execute(
            plan,
            project_id=runtime.project_id,
            question=question,
            limit=LIMIT,
            conversation_memory="",
        )
        answer = result.answer
        references = list(result.references)
        graph_nodes = list(result.graph_nodes)
        graph_edges = list(result.graph_edges)
        uncertainties = list(result.uncertainties)
    except Exception as error:
        status = "error"
        error_record = {
            "type": type(error).__name__,
            "message": sanitize_error_message(error),
        }
    finally:
        runtime.response_recorder.end_case()
    call_deltas = {
        "agent_llm": int(runtime.llm_counters.calls) - before_calls["agent_llm"],
        "query_embedding": int(runtime.embedding_counters.calls) - before_calls["query_embedding"],
        "rewrite_llm": int(runtime.rewrite_counters.calls) - before_calls["rewrite_llm"],
    }
    call_delta = call_deltas["agent_llm"]
    response_events = runtime.response_recorder.slice(
        before_response_ordinal,
        int(runtime.response_recorder.event_count),
    )
    repair_events = [event for event in response_events if event.get("phase") == "repair"]
    repair_attempted = bool(repair_events)
    guard_failure = (
        answer == EVIDENCE_VALIDATION_FAILED_ANSWER
        or "Evidence validation repair limit reached." in uncertainties
    )
    final_validation = _citation_validation(answer, references)
    final_evidence_validation_passed = (
        status == "ok"
        and not guard_failure
        and final_validation["is_valid"] is True
    )
    # A successful provider response is not a successful evidence repair.  The
    # repaired answer must also survive the same final evidence validator used
    # by the product service; fallback/repair-limit results are failures.
    repair_succeeded = repair_attempted and final_evidence_validation_passed
    repair_failed = repair_attempted and not final_evidence_validation_passed
    record = {
        **dict(runtime.identity),
        "question_id": str(case["question_id"]),
        "variant": variant,
        "run_index": run_index,
        "question": question,
        "language": case.get("language"),
        "difficulty": case.get("difficulty"),
        "source_answerable": case.get("source_answerable"),
        "system_answerable": case.get("system_answerable"),
        "dataset_task_type": str(case.get("task_type", expected)),
        "expected_task_type": expected,
        "planned_task_type": planned,
        "answer": answer,
        "references": [_serialize_reference(item, runtime.entity_keys) for item in references],
        "graph_nodes": [_serialize_node(item, runtime.entity_keys) for item in graph_nodes],
        "graph_edges": [_serialize_edge(item, runtime.entity_keys) for item in graph_edges],
        "uncertainties": uncertainties,
        "status": status,
        "error": error_record,
        "provider_llm_call_delta": call_delta,
        "provider_call_deltas": call_deltas,
        "llm_response_events": response_events,
        "rewrite": _rewrite_details(runtime.rewriter, question),
        "wall_latency_seconds": time.perf_counter() - started,
        "citation_validation": final_validation,
        "final_evidence_validation_passed": final_evidence_validation_passed,
        "guard_failure_inferred": guard_failure,
        "repair_attempted_inferred": repair_attempted,
        "repair_attempted_corroborated_by_responses": repair_attempted,
        "repair_call_delta_indicated": call_delta >= 2,
        "repair_succeeded": repair_succeeded,
        "repair_failed": repair_failed,
    }
    return record


@dataclass(frozen=True)
class ResumeState:
    records: int
    orphan_calls: Mapping[str, int]


def require_no_unconfirmed_provider_calls(counters: Mapping[str, Any]) -> None:
    pending = {
        name: int(getattr(counter, "pending", 0))
        for name, counter in counters.items()
        if int(getattr(counter, "pending", 0)) > 0
    }
    if pending:
        details = ", ".join(f"{name}={count}" for name, count in sorted(pending.items()))
        raise RuntimeError(
            f"unconfirmed provider calls remain ({details}); refusing to call providers"
        )


def require_no_orphan_provider_calls(state: ResumeState) -> None:
    orphaned = {
        name: int(count) for name, count in state.orphan_calls.items() if int(count) > 0
    }
    if orphaned:
        details = ", ".join(f"{name}={count}" for name, count in sorted(orphaned.items()))
        raise RuntimeError(
            f"orphan provider calls are not checkpointed ({details}); refusing automatic resend"
        )


def validate_resume_state(
    path: Path,
    identity: Mapping[str, str],
    ledger_calls: Mapping[str, int],
    *,
    expected_keys: set[tuple[str, str, int]],
    require_complete: bool = False,
) -> ResumeState:
    """Validate every checkpoint identity and reconcile durable LLM calls."""
    if not path.exists():
        return ResumeState(
            records=0,
            orphan_calls={name: int(value) for name, value in ledger_calls.items()},
        )
    JsonlCheckpointWriter(path)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    observed_keys: set[tuple[str, str, int]] = set()
    recorded_calls = {name: 0 for name in ledger_calls}
    for line_number, record in enumerate(records, start=1):
        if any(record.get(field) != identity.get(field) for field in RAW_IDENTITY_FIELDS):
            raise ValueError(f"raw checkpoint identity mismatch at {path}:{line_number}")
        key = (str(record.get("question_id")), str(record.get("variant")), record.get("run_index"))
        if key in observed_keys:
            raise ValueError(f"duplicate raw checkpoint key at {path}:{line_number}: {key}")
        if key not in expected_keys:
            raise ValueError(f"raw checkpoint key outside expected schedule at {path}:{line_number}: {key}")
        observed_keys.add(key)
        deltas = record.get("provider_call_deltas")
        if not isinstance(deltas, Mapping):
            raise ValueError(f"raw checkpoint lacks provider_call_deltas at {path}:{line_number}")
        for name in recorded_calls:
            recorded_calls[name] += int(deltas.get(name, 0))
    if len(records) != len(observed_keys):
        raise ValueError("raw checkpoint line count does not equal unique key count")
    orphan_calls: dict[str, int] = {}
    for name, actual in ledger_calls.items():
        accounted = recorded_calls[name]
        if accounted > int(actual):
            raise ValueError(
                f"raw records account for {accounted} {name} calls, ledger has {actual}"
            )
        orphan_calls[name] = int(actual) - accounted
    if require_complete and observed_keys != expected_keys:
        missing = sorted(expected_keys - observed_keys)
        raise ValueError(f"raw checkpoint schedule is incomplete; missing {len(missing)} keys")
    return ResumeState(records=len(records), orphan_calls=orphan_calls)


def write_ablation_status(path: Path, identity: Mapping[str, str]) -> None:
    write_metadata(path, {
        "identity": dict(identity),
        "A7": {
            "status": "not_executable",
            "reason": "The canonical dataset has no multi-turn cases; conversation memory cannot be ablated fairly.",
        },
        "A8": {
            "status": "executable",
            "reason": "AnswerEvidenceValidator is replaced by an explicit AlwaysValid validator, removing guard and repair.",
        },
        "A9": {
            "status": "not_executable",
            "reason": "Task services expose no fair validate-but-no-repair hook; this must not be conflated with A8.",
        },
    })


def require_verified_retrieval_provenance(
    metadata: Mapping[str, Any],
    identity: Mapping[str, str],
) -> Mapping[str, Any]:
    """Fail closed unless the index build is pinned to the same inputs."""
    for field in ("dataset_sha256", "repo_commit", "db_sha256", "snapshot_sha256"):
        if metadata.get(field) != identity.get(field):
            raise RuntimeError(f"retrieval provenance mismatch for {field}")
    build = metadata.get("build")
    original = build.get("original_build", build) if isinstance(build, Mapping) else None
    if not isinstance(original, Mapping) or original.get("status") != "completed":
        raise RuntimeError("retrieval provenance mismatch: verified completed build required")
    for field in ("db_sha256", "snapshot_sha256"):
        if original.get(field) != identity.get(field):
            raise RuntimeError(f"retrieval provenance mismatch for build {field}")
    return build


def require_current_retrieval_config(
    metadata: Mapping[str, Any],
    settings: Any,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Compare pinned retrieval provenance with current effective inputs."""
    from stage2b_retrieval import retrieval_config

    current = retrieval_config(settings, args)
    current_fingerprint = config_fingerprint(current)
    if metadata.get("effective_config") != current:
        raise RuntimeError("current retrieval config does not match retrieval metadata")
    if metadata.get("config_fingerprint") != current_fingerprint:
        raise RuntimeError("current retrieval config fingerprint does not match retrieval metadata")
    return current


def agent_config(settings: Any, retrieval_metadata: Mapping[str, Any]) -> dict[str, Any]:
    from stage2b_retrieval import canonical_endpoint

    return {
        "retrieval_config_fingerprint": retrieval_metadata["config_fingerprint"],
        "llm_model": settings.llm_model,
        "llm_endpoint": canonical_endpoint(settings.llm_base_url),
        "rag_max_context_chars": settings.rag_max_context_chars,
        "limit": LIMIT,
        "llm_reproducibility": {
            "temperature": 0,
            "seed": "not_requested/provider_support_unknown",
            "raw_response_capture_enabled": True,
            "write_ahead_call_accounting": True,
        },
        "variants": {
            "B5": {"evidence_validator": "AnswerEvidenceValidator"},
            "A8": {"evidence_validator": "AlwaysValidEvidenceValidator"},
            "A7": {"status": "not_executable"},
            "A9": {"status": "not_executable"},
        },
    }


def _make_executor(retrieval_runtime: Any, settings: Any, llm: Any, validator: Any) -> Any:
    from app.agent.executor import AgentExecutor
    from app.graph.query_service import GraphQueryService
    from app.rag.context_builder import RagContextBuilder
    from app.rag.graph_context_builder import GraphContextBuilder
    from app.rag.graph_retriever import GraphRagRetriever
    from app.retrieval.hybrid_search import HybridSearchService
    from app.services.change_plan_service import ChangePlanService
    from app.services.code_qa_service import CodeQaService
    from app.services.trace_service import TraceService

    search = HybridSearchService(
        embeddings=retrieval_runtime.embeddings,
        vector_store=retrieval_runtime.vector_store,
        keyword_search=retrieval_runtime.keyword_search,
        rewriter=retrieval_runtime.rewriter,
    )
    graph = retrieval_runtime.graph_query
    rag_context = RagContextBuilder(settings.rag_max_context_chars)
    graph_context = GraphContextBuilder(settings.rag_max_context_chars)
    return AgentExecutor(
        code_qa=CodeQaService(search=search, context_builder=rag_context, llm=llm, evidence_validator=validator),
        trace=TraceService(
            retriever=GraphRagRetriever(search=search, graph=graph),
            graph=graph,
            context_builder=graph_context,
            llm=llm,
            evidence_validator=validator,
        ),
        change_plan=ChangePlanService(
            search=search,
            graph=graph,
            context_builder=graph_context,
            llm=llm,
            evidence_validator=validator,
        ),
    )


def compose_agent_runtime(args: argparse.Namespace, retrieval_metadata: Mapping[str, Any]) -> tuple[AgentRuntime, Any, Any]:
    """Compose real product services while reusing the audited vector runtime."""
    from openai import OpenAI
    from app.agent.planner import SimpleAgentPlanner
    from app.llm.client import OpenAICompatibleLlmClient
    from app.services.evidence_validator import AnswerEvidenceValidator
    from stage2b_retrieval import compose_runtime

    retrieval_runtime, context, session, qdrant = compose_runtime(args)
    from stage2b_retrieval import canonical_endpoint

    expected = {
        "config_fingerprint": config_fingerprint(args.current_retrieval_config),
        "qdrant_path": str(args.qdrant_path.resolve()),
        "db_sha256": args.identity["db_sha256"],
        "snapshot_sha256": args.identity["snapshot_sha256"],
        "project_id": retrieval_runtime.project_id,
        "project_count": context["project_count"],
        "entity_count": len(context["entities"]),
        "relation_count": context["relation_count"],
        "embedding_model": args.settings.embedding_model,
        "embedding_dimensions": args.settings.embedding_dimensions,
        "embedding_endpoint": canonical_endpoint(args.settings.embedding_base_url),
        "collection": retrieval_runtime.vector_store.collection_name(retrieval_runtime.project_id),
    }
    verify_reusable_index(
        retrieval_runtime.vector_store,
        retrieval_runtime.project_id,
        retrieval_metadata["build"],
        expected,
    )
    counters = DurableCallCounters(args.ledger_dir / args.run_id / "agent_llm.jsonl")
    response_recorder = DurableLlmResponseRecorder(
        args.ledger_dir / args.run_id / "agent_llm_responses.jsonl"
    )
    raw = OpenAI(api_key=args.settings.llm_api_key, base_url=args.settings.llm_base_url, max_retries=0)
    recorded_raw = ResponseRecordingOpenAIClient(raw, response_recorder, counters)
    llm = OpenAICompatibleLlmClient(
        args.settings.llm_model,
        args.settings.llm_api_key,
        base_url=args.settings.llm_base_url,
        client=recorded_raw,
    )
    runtime = AgentRuntime(
        project_id=retrieval_runtime.project_id,
        entity_keys=retrieval_runtime.entity_keys,
        planner=SimpleAgentPlanner(),
        executor=_make_executor(retrieval_runtime, args.settings, llm, AnswerEvidenceValidator()),
        a8_executor=_make_executor(retrieval_runtime, args.settings, llm, AlwaysValidEvidenceValidator()),
        llm_counters=counters,
        embedding_counters=context["embedding_provider_counters"],
        rewrite_counters=context["rewrite_provider_counters"],
        response_recorder=response_recorder,
        rewriter=retrieval_runtime.rewriter,
        identity=args.identity,
    )
    return runtime, session, qdrant


def run_schedule(
    schedule: Sequence[tuple[str, int, Mapping[str, Any]]],
    runtime: AgentRuntime,
    output: Path,
) -> int:
    written = 0
    with JsonlCheckpointWriter(output) as checkpoint:
        for variant, run_index, case in schedule:
            question_id = str(case["question_id"])
            if checkpoint.is_completed(question_id, variant, run_index):
                continue
            record = evaluate_agent_case(case, variant, run_index, runtime)
            if checkpoint.append(record):
                written += 1
    return written


def _atomic_write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(dict(record), ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run_agent_smoke_gate(
    schedule: Sequence[tuple[str, int, Mapping[str, Any]]],
    runtime: AgentRuntime,
    canonical_output: Path,
) -> list[dict[str, Any]]:
    """Evaluate two probes in isolation and atomically promote only success."""
    if len(schedule) != 2:
        raise ValueError("agent smoke gate requires exactly two cases")
    temporary = canonical_output.with_name(
        f".{canonical_output.name}.smoke-{uuid.uuid4().hex}.tmp.jsonl"
    )
    run_schedule(schedule, runtime, temporary)
    smoke_records = [
        json.loads(line)
        for line in temporary.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failed = [record for record in smoke_records if record.get("status") != "ok"]
    if failed:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        failed_path = canonical_output.with_name(
            f"{canonical_output.stem}.smoke-failed-{stamp}{canonical_output.suffix}"
        )
        os.replace(temporary, failed_path)
        raise RuntimeError(
            f"smoke agent failed for {len(failed)} record(s); preserved at {failed_path}"
        )

    existing: list[dict[str, Any]] = []
    if canonical_output.exists():
        existing = [
            json.loads(line)
            for line in canonical_output.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for line_number, record in enumerate(existing, start=1):
            if any(record.get(field) != runtime.identity.get(field) for field in RAW_IDENTITY_FIELDS):
                raise ValueError(
                    f"raw checkpoint identity mismatch at {canonical_output}:{line_number}"
                )
    merged = list(existing)
    keys = {checkpoint_key(record) for record in existing}
    for record in smoke_records:
        key = checkpoint_key(record)
        if key not in keys:
            merged.append(record)
            keys.add(key)
    _atomic_write_jsonl(canonical_output, merged)
    temporary.unlink(missing_ok=True)
    return smoke_records


def llm_reproducibility_metadata(
    recorder: Any,
    *,
    requested_model: str,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    events = recorder.slice(0, recorder.event_count)
    successful = [event for event in events if event.get("error") is None]
    versions = sorted({
        str(event["returned_model_version"])
        for event in successful
        if event.get("returned_model_version")
    })
    available = [event for event in successful if event.get("usage_available")]
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "temperature": 0,
        "seed": "not_requested/provider_support_unknown",
        "requested_model": requested_model,
        "returned_model_versions_observed": versions,
        "usage_totals": {
            name: sum(int(event.get(name) or 0) for event in available)
            for name in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "usage_available_events": len(available),
        "usage_unavailable_events": len(successful) - len(available),
        "failed_response_events": len(events) - len(successful),
        "raw_response_capture_enabled": True,
        "response_event_count": len(events),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Stage 2B end-to-end Agent variants")
    parser.add_argument("--env-file", type=Path, default=BACKEND_DIR / ".env")
    parser.add_argument("--db", type=Path, default=ROOT / "evaluation/runtime/pilot/rca_eval.db")
    parser.add_argument("--qdrant-path", type=Path, default=ROOT / "evaluation/runtime/pilot/stage2b_qdrant")
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/pilot-current.jsonl")
    parser.add_argument("--dataset-sha", required=True)
    parser.add_argument("--repo-commit", required=True)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "evaluation/runtime/pilot/snapshot/manifest.json")
    parser.add_argument("--retrieval-metadata", type=Path, default=ROOT / "evaluation/results/raw/stage2b_retrieval.metadata.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results/raw/stage2b_agent.jsonl")
    parser.add_argument("--metadata", type=Path, default=ROOT / "evaluation/results/raw/stage2b_agent.metadata.json")
    parser.add_argument("--ablation-status", type=Path, default=ROOT / "evaluation/results/raw/stage2b_agent.ablations.json")
    parser.add_argument("--ledger-dir", type=Path, default=ROOT / "evaluation/runtime/pilot/stage2b_provider_ledgers")
    parser.add_argument("--run-id")
    parser.add_argument("--smoke", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    from app.core.config import Settings

    args = build_parser().parse_args(argv)
    dataset_sha = verify_sha256(args.dataset, args.dataset_sha)
    db_sha = sha256_file(args.db)
    snapshot_sha = sha256_file(args.snapshot)
    retrieval_metadata = json.loads(args.retrieval_metadata.read_text(encoding="utf-8"))
    settings = Settings(_env_file=args.env_file)
    current_retrieval_config = require_current_retrieval_config(
        retrieval_metadata, settings, args
    )
    config = agent_config(settings, retrieval_metadata)
    fingerprint = config_fingerprint(config)
    previous = json.loads(args.metadata.read_text(encoding="utf-8")) if args.metadata.exists() else None
    run_id = resolve_run_id(previous, args.run_id, dataset_sha, args.repo_commit, db_sha, snapshot_sha, fingerprint)
    identity = {
        "run_id": run_id,
        "dataset_sha256": dataset_sha,
        "repo_commit": args.repo_commit,
        "db_sha256": db_sha,
        "snapshot_sha256": snapshot_sha,
        "config_fingerprint": fingerprint,
    }
    require_verified_retrieval_provenance(retrieval_metadata, identity)
    args.run_id = run_id
    args.settings = settings
    args.identity = identity
    args.current_retrieval_config = current_retrieval_config
    started_at = str((previous or {}).get("started_at") or _utc_now())
    write_metadata(args.metadata, {
        **identity,
        "dataset_path": str(args.dataset),
        "effective_config": config,
        "started_at": started_at,
        "status": "in_progress",
    })
    cases = load_dataset(args.dataset)
    schedule = build_run_schedule(cases)
    if args.smoke:
        schedule = [("B5", 0, cases[0]), ("B5", 0, cases[1])]
    expected_keys = schedule_keys(schedule)
    runtime, session, qdrant = compose_agent_runtime(args, retrieval_metadata)
    try:
        runtime.response_recorder.reconcile_pending(runtime.llm_counters)
        require_no_unconfirmed_provider_calls({
            "agent_llm": runtime.llm_counters,
            "query_embedding": runtime.embedding_counters,
            "rewrite_llm": runtime.rewrite_counters,
        })
        ledger_calls = {
            "agent_llm": runtime.llm_counters.calls,
            "query_embedding": runtime.embedding_counters.calls,
            "rewrite_llm": runtime.rewrite_counters.calls,
        }
        resume = validate_resume_state(
            args.output, identity, ledger_calls, expected_keys=expected_keys
        )
        require_no_orphan_provider_calls(resume)
        write_ablation_status(args.ablation_status, identity)
        if args.smoke:
            run_agent_smoke_gate(schedule, runtime, args.output)
        else:
            run_schedule(schedule, runtime, args.output)
        runtime.response_recorder.validate_against(runtime.llm_counters)
        final_ledgers = {
            "agent_llm": runtime.llm_counters.calls,
            "query_embedding": runtime.embedding_counters.calls,
            "rewrite_llm": runtime.rewrite_counters.calls,
        }
        completed = validate_resume_state(
            args.output,
            identity,
            final_ledgers,
            expected_keys=expected_keys,
            require_complete=True,
        )
        total = count_validated_records(args.output, identity)
        finished_at = _utc_now()
        reproducibility = llm_reproducibility_metadata(
            runtime.response_recorder,
            requested_model=settings.llm_model,
            started_at=started_at,
            finished_at=finished_at,
        )
        write_metadata(args.metadata, sanitize_provider_metadata({
            **identity,
            "dataset_path": str(args.dataset),
            "effective_config": config,
            "retrieval_run_id": retrieval_metadata["run_id"],
            "records_written": total,
            "status": "completed",
            "records_present_before_resume": resume.records,
            "orphan_provider_calls_before_resume": dict(resume.orphan_calls),
            "orphan_provider_calls_after_run": dict(completed.orphan_calls),
            "provider_counters": {
                "agent_llm_sdk_create_attempts": runtime.llm_counters.to_dict(),
                "query_embedding_sdk_create_attempts": runtime.embedding_counters.to_dict(),
                "rewrite_llm_sdk_create_attempts": runtime.rewrite_counters.to_dict(),
            },
            "providers": {
                "agent_llm": {"model": settings.llm_model, "base_url": settings.llm_base_url},
                "sdk_retries_disabled": True,
            },
            "llm_reproducibility": reproducibility,
            "started_at": started_at,
            "finished_at": finished_at,
            "temperature": reproducibility["temperature"],
            "seed": reproducibility["seed"],
            "model_requested": reproducibility["requested_model"],
            "returned_model_versions_observed": reproducibility["returned_model_versions_observed"],
            "raw_response_capture_enabled": True,
            "default_metrics_variant": "B5",
            "a8_separate_from_default_metrics": True,
            "stability_subset": stability_subset_summary(cases),
        }))
    finally:
        session.close()
        close = getattr(qdrant, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
