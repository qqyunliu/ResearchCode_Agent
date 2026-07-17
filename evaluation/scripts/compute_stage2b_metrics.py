"""Deterministic Stage 2B metrics; no model-based judging is performed."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


RUNNERS_DIR = Path(__file__).resolve().parents[1] / "runners"
if str(RUNNERS_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNERS_DIR))

from baseline_contract import build_identity, config_fingerprint


RETRIEVAL_VARIANTS = ("B2", "B3", "A1", "A2", "A3", "A4")
GRAPH_VARIANTS = ("B4", "A5", "A6")
IDENTITY_FIELDS = ("run_id", "dataset_sha256", "repo_commit")
RAW_IDENTITY_FIELDS = (
    "run_id", "dataset_sha256", "repo_commit", "config_fingerprint",
    "db_sha256", "snapshot_sha256",
)
SNAPSHOT_ATTESTATION_VERSION = "3.0.0"
SNAPSHOT_REQUIRED_EXPORTS = {
    "manifest.json", "code_files.json", "code_entities.json",
    "code_relations.json", "frontend_diagnostics.json", "scan_issues.json",
}
RETRIEVAL_PROVIDER_COUNTERS = (
    "embedding_sdk_create_attempts",
    "rewrite_llm_sdk_create_attempts",
)
BRANCH_DIAGNOSTIC_FIELDS = {
    "vector_candidate_count",
    "keyword_candidate_count",
    "overlap_count",
    "keyword_only_count",
    "top10_changed_from_vector",
}


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _mean(values: Sequence[float]) -> float:
    return round(statistics.fmean(values), 4) if values else 0.0


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    interpolated = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(interpolated, 4)


def latency_summary(values: Sequence[float]) -> dict[str, Any]:
    return {
        "n": len(values), "mean": _mean(values),
        "p50": _percentile(values, 0.5), "p95": _percentile(values, 0.95),
        "total": round(sum(values), 4),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_artifact_identity(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = {
        tuple(record.get(field) for field in IDENTITY_FIELDS)
        for record in records
        if any(field in record for field in IDENTITY_FIELDS)
    }
    if len(observed) > 1:
        raise ValueError("artifact identity mismatch across raw records")
    if not observed:
        return {}
    values = next(iter(observed))
    return dict(zip(IDENTITY_FIELDS, values, strict=True))


def canonical_cases(dataset: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[str] = set()
    eligible = []
    for case in dataset:
        for field in ("dataset_version", "question_id", "repo_id", "commit_sha"):
            if not case.get(field):
                raise ValueError(f"dataset identity field {field} is required on every record")
        question_id = str(case["question_id"])
        if question_id in seen:
            raise ValueError(f"duplicate dataset question_id: {question_id}")
        seen.add(question_id)
        if (
            case.get("gold_status") == "machine_verified"
            and case.get("annotation", {}).get("review_status") == "accepted"
            and case.get("execution_status") in {"executable", "executed"}
        ):
            eligible.append(case)
    if not eligible:
        raise ValueError("canonical machine_verified/accepted eligible dataset is empty")
    return eligible


def select_stability_question_ids(
    cases: Sequence[Mapping[str, Any]], size: int = 8,
) -> list[str]:
    """Mirror the runner's deterministic stratified hard-case selection."""
    if len(cases) < size:
        raise ValueError(f"stability subset requires at least {size} cases")
    ordered = sorted(cases, key=lambda case: str(case["question_id"]))
    task_values = {str(case.get("expected_task_type", case.get("task_type"))) for case in ordered}
    language_values = {str(case.get("language")) for case in ordered}
    answerability_values = {case.get("source_answerable") for case in ordered}
    if answerability_values - {True, False}:
        raise ValueError("stability cases require boolean source_answerable")
    if len(task_values) < 3 or not {"zh", "en"} <= language_values or len(answerability_values) < 2:
        raise ValueError("cases cannot satisfy the required stability strata")
    uncovered: set[tuple[str, object]] = {
        *(("task", value) for value in task_values),
        *(("language", value) for value in ("zh", "en")),
        *(("answerable", value) for value in (True, False)),
    }
    difficulty_rank = {"hard": 3, "medium": 2, "easy": 1}
    selected = []
    remaining = list(ordered)
    while len(selected) < size:
        def candidate_key(case: Mapping[str, Any]) -> tuple[int, int, int, str]:
            categories = {
                ("task", str(case.get("expected_task_type", case.get("task_type")))),
                ("language", str(case.get("language"))),
                ("answerable", case.get("source_answerable")),
            }
            return (
                len(categories & uncovered),
                difficulty_rank.get(str(case.get("difficulty", "easy")), 0),
                int(case.get("source_answerable") is False),
                str(case["question_id"]),
            )
        chosen = max(remaining, key=candidate_key)
        remaining.remove(chosen)
        selected.append(chosen)
        uncovered -= {
            ("task", str(chosen.get("expected_task_type", chosen.get("task_type")))),
            ("language", str(chosen.get("language"))),
            ("answerable", chosen.get("source_answerable")),
        }
    if uncovered:
        raise ValueError(f"stability subset did not cover strata: {sorted(uncovered)!r}")
    return sorted(str(case["question_id"]) for case in selected)


def _record_key(record: Mapping[str, Any]) -> tuple[str, str, int]:
    run_index = record.get("run_index")
    if type(run_index) is not int or run_index < 0:
        raise ValueError("raw schedule requires non-negative integer run_index")
    return str(record.get("question_id")), str(record.get("variant")), run_index


def _validate_raw(
    records: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    expected: set[tuple[str, str, int]],
    dataset_sha256: str,
    label: str,
) -> None:
    if metadata.get("status") != "completed":
        raise ValueError(f"{label} metadata status must be completed")
    if int(metadata.get("records_written", -1)) != len(expected):
        raise ValueError(f"{label} metadata records_written does not equal exact schedule")
    keys: set[tuple[str, str, int]] = set()
    for line_number, record in enumerate(records, 1):
        if any(not record.get(field) for field in RAW_IDENTITY_FIELDS):
            raise ValueError(f"{label} raw identity incomplete at line {line_number}")
        for field in RAW_IDENTITY_FIELDS:
            if record.get(field) != metadata.get(field):
                raise ValueError(f"{label} raw/metadata identity mismatch for {field}")
        if record.get("dataset_sha256") != dataset_sha256:
            raise ValueError(f"{label} raw dataset SHA mismatch")
        key = _record_key(record)
        if key in keys:
            raise ValueError(f"{label} raw duplicate schedule key: {key}")
        keys.add(key)
        events = record.get("llm_response_events", [])
        attempts = [event.get("attempt_id") for event in events]
        if len(attempts) != len(set(attempts)) or any(not item for item in attempts):
            raise ValueError(f"{label} response events require unique attempt_id")
        if any(event.get("phase") not in {"initial", "repair"} for event in events):
            raise ValueError(f"{label} response event phase is invalid")
    if keys != expected:
        raise ValueError(f"{label} raw schedule mismatch: expected {len(expected)}, got {len(keys)}")


def _validate_retrieval_only_integrity(
    records: Sequence[Mapping[str, Any]], metadata: Mapping[str, Any]
) -> None:
    for line_number, record in enumerate(records, 1):
        if record.get("status") != "ok":
            raise ValueError(
                f"retrieval-only raw status must be ok at line {line_number}"
            )
        if record.get("variant") not in {"B3", "A1", "A2", "A3", "A4"}:
            continue
        diagnostics = record.get("branch_diagnostics")
        if not isinstance(diagnostics, Mapping) or set(diagnostics) != BRANCH_DIAGNOSTIC_FIELDS:
            raise ValueError(
                f"retrieval-only branch_diagnostics is incomplete at line {line_number}"
            )
        counts: dict[str, int] = {}
        for field in (
            "vector_candidate_count",
            "keyword_candidate_count",
            "overlap_count",
            "keyword_only_count",
        ):
            value = diagnostics.get(field)
            if type(value) is not int or value < 0:
                raise ValueError(
                    f"retrieval-only branch_diagnostics {field} must be a non-negative integer"
                )
            counts[field] = value
        if type(diagnostics.get("top10_changed_from_vector")) is not bool:
            raise ValueError(
                "retrieval-only branch_diagnostics top10_changed_from_vector must be boolean"
            )
        if counts["overlap_count"] > min(
            counts["vector_candidate_count"], counts["keyword_candidate_count"]
        ):
            raise ValueError("retrieval-only branch_diagnostics overlap_count is inconsistent")
        if counts["keyword_only_count"] != (
            counts["keyword_candidate_count"] - counts["overlap_count"]
        ):
            raise ValueError("retrieval-only branch_diagnostics keyword_only_count is inconsistent")

    counters = metadata.get("provider_counters")
    summary = metadata.get("provider_ledger_summary")
    if not isinstance(counters, Mapping) or not isinstance(summary, Mapping):
        raise ValueError("retrieval-only provider counters and ledger summary are required")
    if set(counters) != set(RETRIEVAL_PROVIDER_COUNTERS) or set(summary) != set(
        RETRIEVAL_PROVIDER_COUNTERS
    ):
        raise ValueError("retrieval-only provider counter keys are incomplete")
    for provider in RETRIEVAL_PROVIDER_COUNTERS:
        counter = counters.get(provider)
        ledger = summary.get(provider)
        if not isinstance(counter, Mapping) or not isinstance(ledger, Mapping):
            raise ValueError(f"retrieval-only {provider} counter structure is invalid")
        for field in ("pending", "unconfirmed"):
            if type(counter.get(field)) is not int or counter.get(field) != 0:
                raise ValueError(f"retrieval-only {provider} {field} must be zero")
            if type(ledger.get(field)) is not int or ledger.get(field) != 0:
                raise ValueError(f"retrieval-only {provider} ledger {field} must be zero")
        if type(ledger.get("orphan")) is not int or ledger.get("orphan") != 0:
            raise ValueError(f"retrieval-only {provider} orphan must be zero")


def validate_formal_artifacts(
    dataset: Sequence[Mapping[str, Any]],
    retrieval_records: Sequence[Mapping[str, Any]],
    agent_records: Sequence[Mapping[str, Any]],
    retrieval_metadata: Mapping[str, Any],
    agent_metadata: Mapping[str, Any] | None,
    dataset_sha256: str,
    *,
    retrieval_only: bool = False,
) -> list[Mapping[str, Any]]:
    eligible = canonical_cases(dataset)
    if len(eligible) != 36:
        raise ValueError(f"formal Stage 2B requires exactly 36 eligible cases, got {len(eligible)}")
    commits = {str(case["commit_sha"]) for case in dataset}
    if len(commits) != 1:
        raise ValueError("dataset repository commit identity is inconsistent")
    commit = next(iter(commits))
    metadata_items: list[tuple[str, Mapping[str, Any]]] = [
        ("retrieval", retrieval_metadata)
    ]
    if not retrieval_only:
        if agent_metadata is None:
            raise ValueError("agent metadata is required for complete formal Stage 2B")
        metadata_items.append(("agent", agent_metadata))
    for label, metadata in metadata_items:
        if metadata.get("dataset_sha256") != dataset_sha256:
            raise ValueError(f"{label} metadata dataset SHA mismatch")
        if metadata.get("repo_commit") != commit:
            raise ValueError(f"{label} metadata repository commit mismatch")
        if not metadata.get("config_fingerprint") or not metadata.get("run_id"):
            raise ValueError(f"{label} metadata config/run identity incomplete")
    retrieval_ids = {
        str(case["question_id"])
        for case in eligible
        if "retrieval" in case.get("evaluation_layers", [])
    }
    all_retrieval_variants = (*RETRIEVAL_VARIANTS, *GRAPH_VARIANTS)
    reported_variants = retrieval_metadata.get("selected_variants")
    if retrieval_only:
        if not isinstance(reported_variants, list) or tuple(reported_variants) != RETRIEVAL_VARIANTS:
            raise ValueError(
                "retrieval-only formal metadata selected_variants must exactly match the six direct retrieval variants"
            )
        retrieval_variants = tuple(reported_variants)
    else:
        if reported_variants is not None and tuple(reported_variants) != all_retrieval_variants:
            raise ValueError(
                "complete formal Stage 2B selected_variants must contain all nine retrieval variants"
            )
        retrieval_variants = all_retrieval_variants
    retrieval_expected = {
        (question_id, variant, 0)
        for question_id in retrieval_ids
        for variant in retrieval_variants
    }
    _validate_raw(retrieval_records, retrieval_metadata, retrieval_expected, dataset_sha256, "retrieval")
    if retrieval_only:
        _validate_retrieval_only_integrity(retrieval_records, retrieval_metadata)
        if agent_records or agent_metadata is not None:
            raise ValueError("retrieval-only formal mode does not accept agent artifacts")
        return eligible
    assert agent_metadata is not None
    reported_stability_ids = [
        str(item)
        for item in agent_metadata.get("stability_subset", {}).get("question_ids", [])
    ]
    expected_stability_ids = select_stability_question_ids(eligible)
    if len(reported_stability_ids) != 8 or sorted(reported_stability_ids) != expected_stability_ids:
        raise ValueError("agent stability subset does not match deterministic 8-case dataset selection")
    stability_ids = set(expected_stability_ids)
    eligible_ids = {str(case["question_id"]) for case in eligible}
    if not stability_ids <= eligible_ids:
        raise ValueError("agent stability subset contains unknown question IDs")
    agent_expected = {
        *((question_id, variant, 0) for question_id in eligible_ids for variant in ("B5", "A8")),
        *((question_id, "B5", run_index) for question_id in stability_ids for run_index in (1, 2)),
    }
    if len(agent_expected) != 88:
        raise ValueError("formal Stage 2B agent schedule must contain exactly 88 records")
    _validate_raw(agent_records, agent_metadata, agent_expected, dataset_sha256, "agent")
    return eligible


def validate_baseline_identity(baseline: Mapping[str, Any], dataset_sha256: str) -> None:
    if not baseline.get("dataset_sha256") or baseline.get("dataset_sha256") != dataset_sha256:
        raise ValueError("B0/B1 dataset_sha256 is required and must match Stage 2B dataset")


def validate_baseline_cli_pair(name: str, raw_path: Path | None, metadata_path: Path | None) -> None:
    if (raw_path is None) != (metadata_path is None):
        raise ValueError(f"{name} raw and metadata paths must be supplied together")


def validate_baseline_artifact(
    name: str,
    records: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    expected_question_ids: set[str],
    dataset_sha256: str,
    repo_commit: str,
) -> None:
    """Fail closed unless raw and sidecar form one canonical baseline run."""
    if len(expected_question_ids) != 36:
        raise ValueError(f"{name} formal baseline schedule must contain exactly 36 questions")
    if metadata.get("status") != "completed":
        raise ValueError(f"{name} metadata status must be completed")
    if metadata.get("records_written") != 36 or len(records) != 36:
        raise ValueError(f"{name} metadata records_written must equal the exact 36-record schedule")
    effective_config = metadata.get("effective_config")
    if not isinstance(effective_config, Mapping):
        raise ValueError(f"{name} metadata effective_config is required")
    canonical = {
        "contract_version": 1,
        "ranking_unit": "file",
        "top_k": 10,
        "variant": name,
    }
    if dict(effective_config) != canonical:
        raise ValueError(f"{name} metadata effective_config is not the canonical runner contract")
    recomputed_fingerprint = config_fingerprint(effective_config)
    if metadata.get("config_fingerprint") != recomputed_fingerprint:
        raise ValueError(f"{name} metadata config fingerprint does not match effective_config")
    expected_identity = build_identity(name, dataset_sha256, repo_commit, 10)
    for field in ("run_id", "dataset_sha256", "repo_commit", "config_fingerprint", "variant", "run_index"):
        if metadata.get(field) != expected_identity[field]:
            raise ValueError(f"{name} metadata identity mismatch for {field}")
    observed_ids: set[str] = set()
    for line_number, record in enumerate(records, 1):
        question_id = str(record.get("question_id", ""))
        if not question_id or question_id in observed_ids or question_id not in expected_question_ids:
            raise ValueError(f"{name} raw exact question schedule mismatch at line {line_number}")
        observed_ids.add(question_id)
        for field in ("run_id", "dataset_sha256", "repo_commit", "config_fingerprint", "variant", "run_index"):
            if record.get(field) != metadata.get(field):
                raise ValueError(f"{name} raw/metadata identity mismatch for {field} at line {line_number}")
    if observed_ids != expected_question_ids:
        raise ValueError(f"{name} raw exact question schedule is incomplete")


def validate_snapshot_binding(
    manifest_path: Path,
    code_files_path: Path,
    retrieval_metadata: Mapping[str, Any],
    agent_metadata: Mapping[str, Any],
) -> Mapping[str, Any]:
    snapshot_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    snapshot_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if retrieval_metadata.get("snapshot_sha256") != snapshot_sha or agent_metadata.get("snapshot_sha256") != snapshot_sha:
        raise ValueError("snapshot manifest hash does not match retrieval/agent metadata")
    commits = {str(retrieval_metadata.get("repo_commit", "")).lower(), str(agent_metadata.get("repo_commit", "")).lower()}
    if len(commits) != 1 or str(snapshot_manifest.get("commit_sha", "")).lower() not in commits:
        raise ValueError("snapshot manifest commit does not match evaluation repository commit")
    if code_files_path.resolve().parent != manifest_path.resolve().parent:
        raise ValueError("snapshot code_files and manifest must come from the same snapshot directory")
    artifact = snapshot_manifest.get("artifacts", {}).get("code_files")
    if not isinstance(artifact, Mapping):
        raise ValueError("snapshot manifest must bind the exact code_files artifact")
    relative_path = Path(str(artifact.get("path", "")))
    if relative_path.is_absolute() or relative_path.as_posix() != "code_files.json":
        raise ValueError("snapshot manifest code_files path must be exactly code_files.json")
    if (manifest_path.parent / relative_path).resolve() != code_files_path.resolve():
        raise ValueError("supplied snapshot code_files does not match manifest binding")
    actual_code_files_sha = hashlib.sha256(code_files_path.read_bytes()).hexdigest()
    if artifact.get("sha256") != actual_code_files_sha:
        raise ValueError("snapshot code_files hash does not match manifest binding")
    return snapshot_manifest


def generate_snapshot_attestation(manifest_path: Path, output_path: Path) -> Mapping[str, Any]:
    """Hash the complete export bundle without changing the original manifest."""
    root = manifest_path.resolve().parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exports = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.glob("*.json"), key=lambda item: item.name)
        if path.resolve() != output_path.resolve() and not path.name.startswith("attestation.")
    }
    missing = SNAPSHOT_REQUIRED_EXPORTS - set(exports)
    if missing:
        raise ValueError(f"snapshot exports missing: {sorted(missing)}")
    payload = {
        "schema_version": SNAPSHOT_ATTESTATION_VERSION,
        "repo_commit": str(manifest.get("commit_sha", "")).lower(),
        "original_manifest": {"path": "manifest.json", "sha256": exports["manifest.json"]},
        "artifacts": {
            name: {"path": name, "sha256": digest}
            for name, digest in sorted(exports.items())
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def validate_snapshot_attestation(
    attestation_path: Path,
    retrieval_metadata: Mapping[str, Any],
    agent_metadata: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    if attestation.get("schema_version") != SNAPSHOT_ATTESTATION_VERSION:
        raise ValueError("snapshot attestation schema_version must be 3.0.0")
    root = attestation_path.resolve().parent
    artifacts = attestation.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("snapshot attestation artifacts must be an object")
    actual_names = {
        path.name for path in root.glob("*.json")
        if path.resolve() != attestation_path.resolve() and not path.name.startswith("attestation.")
    }
    if set(artifacts) != actual_names or not SNAPSHOT_REQUIRED_EXPORTS <= set(artifacts):
        raise ValueError("snapshot attestation must bind the exact exported artifact set")
    for name, entry in artifacts.items():
        if not isinstance(entry, Mapping) or entry.get("path") != name or Path(name).name != name:
            raise ValueError(f"snapshot artifact {name} has a non-canonical path")
        actual_sha = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if entry.get("sha256") != actual_sha:
            raise ValueError(f"snapshot artifact {name} SHA mismatch")
    manifest_sha = artifacts["manifest.json"]["sha256"]
    if attestation.get("original_manifest") != {"path": "manifest.json", "sha256": manifest_sha}:
        raise ValueError("snapshot original manifest binding is inconsistent")
    metadata_items = [retrieval_metadata, *([agent_metadata] if agent_metadata is not None else [])]
    if any(metadata.get("snapshot_sha256") != manifest_sha for metadata in metadata_items):
        raise ValueError("snapshot original manifest SHA does not match runner metadata")
    commits = {str(metadata.get("repo_commit", "")).lower() for metadata in metadata_items}
    if commits != {str(attestation.get("repo_commit", "")).lower()}:
        raise ValueError("snapshot attestation commit does not match runner metadata")
    return attestation


def _gold_entities(case: Mapping[str, Any]) -> set[str]:
    return {
        str(item["stable_entity_key"])
        for item in case.get("gold_entities", [])
        if item.get("indexed_in_system") is True
        and item.get("relevance", "must_recall") == "must_recall"
    }


def _gold_files(case: Mapping[str, Any]) -> set[str]:
    return {
        str(item["file_path"])
        for item in case.get("gold_entities", [])
        if item.get("indexed_in_system") is True
        and item.get("relevance", "must_recall") == "must_recall"
    }


def change_plan_file_gold(case: Mapping[str, Any]) -> dict[str, set[str]]:
    """Keep change-plan file categories separate from retrieval gold."""
    result = {name: set() for name in ("must_change", "likely_change", "context_only", "should_not_change")}
    for item in case.get("gold_files", []):
        if isinstance(item, Mapping) and item.get("category") in result and item.get("file_path"):
            result[str(item["category"])].add(str(item["file_path"]))
    return result


def _refused(record: Mapping[str, Any]) -> bool:
    """Detect explicit refusal without conflating uncertainty disclosure."""
    answer = str(record.get("answer", "")).casefold()
    phrases = (
        "insufficient evidence", "not enough evidence", "cannot determine",
        "cannot answer", "unable to answer", "unable to determine",
        "证据不足", "无法确定", "信息不足", "无法回答", "不能回答",
    )
    structured_fallback = (
        record.get("status") == "error"
        or record.get("guard_failure_inferred") is True
        or "evidence validation repair limit reached" in " ".join(
            str(item).casefold() for item in record.get("uncertainties", [])
        )
    )
    return structured_fallback or any(phrase in answer for phrase in phrases)


def refusal_metrics(
    records: Sequence[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source_unanswerable = []
    source_answerable = []
    source_answerable_full = []
    source_answerable_partial = []
    expected_uncertainty = []
    for record in records:
        case = cases.get(str(record.get("question_id")))
        if not case:
            continue
        if case.get("source_answerable") is False:
            source_unanswerable.append(record)
        else:
            source_answerable.append(record)
            if case.get("system_answerable") == "full":
                source_answerable_full.append(record)
            else:
                source_answerable_partial.append(record)
        if case.get("system_answerable") != "full" or bool(case.get("expected_uncertainties")):
            expected_uncertainty.append(record)
    def detected(population: Sequence[Mapping[str, Any]]) -> float:
        return _rate(sum(_refused(record) for record in population), len(population))
    unanswerable_rate = detected(source_unanswerable)
    answerable_rate = detected(source_answerable)
    return {
        "source_unanswerable_n": len(source_unanswerable),
        "source_unanswerable_refusal_detection_rate": unanswerable_rate,
        "source_answerable_n": len(source_answerable),
        "source_answerable_over_refusal_rate": answerable_rate,
        "source_answerable_full_n": len(source_answerable_full),
        "source_answerable_full_over_refusal_rate": detected(source_answerable_full),
        "source_answerable_partial_or_insufficient_n": len(source_answerable_partial),
        "source_answerable_partial_or_insufficient_over_refusal_rate": detected(source_answerable_partial),
        # Compatibility aliases now follow the corrected source-truth contract.
        "expected_explicit_refusal_n": len(source_unanswerable),
        "explicit_refusal_rate_when_expected": unanswerable_rate,
        "full_answer_population_n": len(source_answerable),
        "unexpected_explicit_refusal_rate": answerable_rate,
        "expected_refusal_n": len(source_unanswerable),
        "correct_refusal_rate": unanswerable_rate,
        "unexpected_refusal_n": len(source_answerable),
        "incorrect_refusal_rate": answerable_rate,
        "expected_uncertainty_n": len(expected_uncertainty),
        "uncertainty_compliance_rate": _rate(
            sum(bool(record.get("uncertainties")) for record in expected_uncertainty),
            len(expected_uncertainty),
        ),
    }


def citation_metrics(
    records: Sequence[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
    snapshot_files: set[str] | None,
) -> dict[str, Any]:
    """Score only reference entries actually selected by answer citation markers."""
    predicted: list[tuple[set[str], set[str]]] = []
    cited_paths: list[str] = []
    eligible = valid_ids = 0
    for record in records:
        case = cases.get(str(record.get("question_id")))
        if not case:
            continue
        references = list(record.get("references", []))
        cited_ids = [int(value) for value in re.findall(r"\[(\d+)\]", str(record.get("answer", "")))]
        selected = []
        for citation_id in cited_ids:
            eligible += 1
            if 1 <= citation_id <= len(references):
                valid_ids += 1
                selected.append(references[citation_id - 1])
        predicted.append((
            {str(item.get("stable_entity_key")) for item in selected if item.get("stable_entity_key")},
            _gold_entities(case),
        ))
        cited_paths.extend(str(item.get("file_path")) for item in selected if item.get("file_path"))
    if not eligible:
        return {
            "eligible_citations": 0, "valid_citation_ids": 0,
            "precision": None, "recall": None, "path_validity_rate": None,
        }
    precision, recall, *_ = _set_pr(predicted)
    path_rate = None if snapshot_files is None else _rate(
        sum(path in snapshot_files for path in cited_paths), len(cited_paths)
    )
    return {
        "eligible_citations": eligible,
        "valid_citation_ids": valid_ids,
        "citation_id_validity_rate": _rate(valid_ids, eligible),
        "precision": precision,
        "recall": recall,
        "path_validity_rate": path_rate,
    }


def response_event_metrics(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    attempt_ids = [event.get("attempt_id") for event in events]
    if any(not attempt_id for attempt_id in attempt_ids) or len(attempt_ids) != len(set(attempt_ids)):
        raise ValueError("response events require unique non-empty attempt_id")
    if any(event.get("phase") not in {"initial", "repair"} for event in events):
        raise ValueError("response event phase must be initial or repair")
    usage_events = [event for event in events if event.get("usage_available") is True]
    models = sorted({
        str(event.get("returned_model") or event.get("requested_model"))
        for event in events if event.get("returned_model") or event.get("requested_model")
    })
    model_versions = sorted({str(event.get("returned_model_version")) for event in events if event.get("returned_model_version")})
    return {
        "attempts": len(events),
        "repair_attempts": sum(event.get("phase") == "repair" for event in events),
        "failed_attempts": sum(bool(event.get("error")) for event in events),
        "usage_available_attempts": len(usage_events),
        "usage_unavailable_attempts": len(events) - len(usage_events),
        "usage": {
            name: sum(int(event.get(name) or 0) for event in usage_events)
            for name in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "models": models,
        "model_versions": model_versions,
        "provider_latency_seconds_total": round(sum(float(event.get("provider_latency_seconds") or 0) for event in events), 4),
    }


def _retrieval_summary(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    key: str,
    predicted_field: str,
) -> dict[str, Any]:
    recalls = {cutoff: [] for cutoff in (1, 5, 10)}
    reciprocal_ranks: list[float] = []
    zero_hits = 0
    for case, record in pairs:
        gold = _gold_entities(case) if key == "entity" else _gold_files(case)
        predicted = [
            str(hit[predicted_field])
            for hit in record.get("hits", [])
            if hit.get(predicted_field)
        ]
        if key == "file":
            predicted = list(dict.fromkeys(predicted))
        for cutoff in recalls:
            recalls[cutoff].append(_rate(len(gold & set(predicted[:cutoff])), len(gold)))
        first = next((rank for rank, value in enumerate(predicted, 1) if value in gold), None)
        reciprocal_ranks.append(1 / first if first else 0.0)
        zero_hits += int(first is None)
    return {
        "n": len(pairs),
        **{f"recall@{cutoff}": _mean(values) for cutoff, values in recalls.items()},
        "mrr": _mean(reciprocal_ranks),
        "zero_hit_rate": _rate(zero_hits, len(pairs)),
    }


def _retrieval_metrics(
    cases: Mapping[str, Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    for variant in RETRIEVAL_VARIANTS:
        variant_records = [
            record for record in records
            if record.get("variant") == variant and record.get("run_index") == 0
        ]
        pairs = [
            (cases[str(record["question_id"])], record)
            for record in variant_records
            if str(record["question_id"]) in cases
            and cases[str(record["question_id"])].get("source_answerable") is True
            and _gold_entities(cases[str(record["question_id"])])
        ]
        result[variant] = {
            "entity": _retrieval_summary(pairs, "entity", "stable_entity_key"),
            "file": _retrieval_summary(pairs, "file", "file_path"),
            "failures": sum(record.get("status") != "ok" for record in variant_records),
            "latency_seconds": latency_summary([
                float(record.get("latency_seconds", 0)) for record in variant_records
            ]),
        }
        unanswerable = [
            record for record in variant_records
            if cases.get(str(record.get("question_id")), {}).get("source_answerable") is False
        ]
        diagnostics[variant] = {
            "n": len(unanswerable),
            "nonempty_hit_rate": _rate(sum(bool(record.get("hits")) for record in unanswerable), len(unanswerable)),
            "error_rate": _rate(sum(record.get("status") != "ok" for record in unanswerable), len(unanswerable)),
        }
    return result, diagnostics


def _gold_nodes(case: Mapping[str, Any]) -> set[str]:
    return {
        str(item["stable_entity_key"])
        for item in case.get("gold_nodes", [])
        if item.get("indexed_in_system") is True
    }


def _edge(item: Mapping[str, Any], predicted: bool = False) -> tuple[str, str, str]:
    source = "source_stable_entity_key" if predicted else "source_key"
    target = "target_stable_entity_key" if predicted else "target_key"
    return str(item.get(source)), str(item.get(target)), str(item.get("relation_type"))


def _gold_edges(case: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    return {
        _edge(item)
        for item in case.get("gold_edges", [])
        if item.get("indexed_in_system") is True
    }


def _source_only_diagnostics(
    cases: Mapping[str, Mapping[str, Any]],
    retrieval_records: Sequence[Mapping[str, Any]],
    agent_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    entity_gold: dict[str, str] = {}
    node_gold: dict[str, str] = {}
    edge_gold: dict[tuple[str, str, str], str] = {}
    for question_id, case in cases.items():
        entity_gold.update({
            str(item["stable_entity_key"]): question_id
            for item in case.get("gold_entities", [])
            if item.get("indexed_in_system") is False and item.get("stable_entity_key")
        })
        node_gold.update({
            str(item["stable_entity_key"]): question_id
            for item in case.get("gold_nodes", [])
            if item.get("indexed_in_system") is False and item.get("stable_entity_key")
        })
        edge_gold.update({
            _edge(item): question_id
            for item in case.get("gold_edges", [])
            if item.get("indexed_in_system") is False
        })
    variants = (*RETRIEVAL_VARIANTS, *GRAPH_VARIANTS, "B5", "A8")
    variant_observations: dict[str, dict[str, set[Any]]] = {}
    for variant in variants:
        records = [
            record for record in (*retrieval_records, *agent_records)
            if record.get("variant") == variant and record.get("run_index") == 0
        ]
        variant_observations[variant] = {
            "entity": {
                str(item.get("stable_entity_key"))
                for record in records
                for field in ("hits", "references")
                for item in record.get(field, [])
                if item.get("stable_entity_key")
            },
            "nodes": {
                str(item.get("stable_entity_key"))
                for record in records for item in record.get("graph_nodes", [])
                if item.get("stable_entity_key")
            },
            "edges": {
                _edge(item, True)
                for record in records for item in record.get("graph_edges", [])
            },
        }
    result = {}
    for component, gold_map in (("entity", entity_gold), ("nodes", node_gold), ("edges", edge_gold)):
        by_variant = {}
        for variant in variants:
            observed = set(gold_map) & variant_observations[variant][component]
            by_variant[variant] = {
                "status": "observed" if observed else "not_observed",
                "observed_count": len(observed),
                "question_ids": sorted({gold_map[item] for item in observed}),
            }
        result[component] = {
            "count": len(gold_map),
            "question_ids": sorted(set(gold_map.values())),
            "excluded_from_main": True,
            "definition": "source-truth gold component with indexed_in_system=false",
            "variants": by_variant,
        }
    return result


def _set_pr(pairs: Iterable[tuple[set[Any], set[Any]]]) -> tuple[float, float, int, int, int]:
    tp = predicted_total = gold_total = 0
    for predicted, gold in pairs:
        tp += len(predicted & gold)
        predicted_total += len(predicted)
        gold_total += len(gold)
    return _rate(tp, predicted_total), _rate(tp, gold_total), tp, predicted_total, gold_total


def _graph_metrics(cases: Mapping[str, Mapping[str, Any]], records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result = {}
    for variant in GRAPH_VARIANTS:
        pairs = []
        for record in records:
            case = cases.get(str(record.get("question_id")))
            if not case or record.get("variant") != variant or record.get("run_index") != 0:
                continue
            graph_gold = (*case.get("gold_nodes", []), *case.get("gold_edges", []))
            if (
                case.get("source_answerable") is True
                and case.get("system_answerable") == "full"
                and graph_gold
                and all(item.get("indexed_in_system") is True for item in graph_gold)
                and (_gold_nodes(case) or _gold_edges(case))
            ):
                pairs.append((case, record))
        node_sets = []
        edge_sets = []
        complete = []
        for case, record in pairs:
            predicted_nodes = {str(item.get("stable_entity_key")) for item in record.get("graph_nodes", []) if item.get("stable_entity_key")}
            predicted_edges = {_edge(item, True) for item in record.get("graph_edges", [])}
            gold_nodes, gold_edges = _gold_nodes(case), _gold_edges(case)
            node_sets.append((predicted_nodes, gold_nodes))
            edge_sets.append((predicted_edges, gold_edges))
            complete.append(gold_nodes <= predicted_nodes and gold_edges <= predicted_edges)
        np, nr, _, _, _ = _set_pr(node_sets)
        ep, er, edge_tp, edge_pred, _ = _set_pr(edge_sets)
        result[variant] = {
            "n": len(pairs),
            "latency_seconds": latency_summary([
                float(record.get("latency_seconds", 0))
                for record in records
                if record.get("variant") == variant and record.get("run_index") == 0
            ]),
            "node_precision": np,
            "node_recall": nr,
            "edge_precision": ep,
            "edge_recall": er,
            "chain_diagnostics": {
                "complete_chain_rate": _rate(sum(complete), len(complete)),
                "partial_chain_coverage": nr,
                "non_gold_edge_rate": _rate(edge_pred - edge_tp, edge_pred),
                "unsupported_stored_edge_rate": 0.0,
                "exact_ordered_chain_match": "not_computable_from_unordered_evidence",
                "note": "Graph raw contains authoritative stored traversal edges but not a canonical ordered path.",
            },
            "diagnostics": {
                "system_partial_n": sum(case.get("source_answerable") is True and case.get("system_answerable") != "full" for case in cases.values()),
                "source_unanswerable_n": sum(case.get("source_answerable") is False for case in cases.values()),
                "nonindexed_graph_gold_n": sum(
                    any(item.get("indexed_in_system") is not True for item in (*case.get("gold_nodes", []), *case.get("gold_edges", [])))
                    for case in cases.values()
                ),
            },
        }
    return result


def _routing(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    labels = sorted({str(record.get("expected_task_type")) for record in records})
    confusion = {label: {predicted: 0 for predicted in labels} for label in labels}
    correct = 0
    f1s = []
    for record in records:
        expected, predicted = str(record.get("expected_task_type")), str(record.get("planned_task_type"))
        confusion.setdefault(expected, {}).setdefault(predicted, 0)
        confusion[expected][predicted] += 1
        correct += int(expected == predicted)
    for label in labels:
        tp = sum(str(r.get("expected_task_type")) == label == str(r.get("planned_task_type")) for r in records)
        fp = sum(str(r.get("expected_task_type")) != label == str(r.get("planned_task_type")) for r in records)
        fn = sum(str(r.get("expected_task_type")) == label != str(r.get("planned_task_type")) for r in records)
        f1s.append(_rate(2 * tp, 2 * tp + fp + fn))
    return {"n": len(records), "accuracy": _rate(correct, len(records)), "macro_f1": _mean(f1s), "confusion_matrix": confusion}


def _agent_variant(
    cases: Mapping[str, Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    snapshot_files: set[str] | None,
) -> dict[str, Any]:
    scored = [record for record in records if record.get("run_index") == 0]
    evidence_pairs = [
        (cases[str(record["question_id"])], record)
        for record in scored
        if cases.get(str(record.get("question_id")), {}).get("source_answerable") is True
        and _gold_entities(cases[str(record["question_id"])])
    ]
    ref_entity = []
    ref_file = []
    range_checks: list[bool] = []
    for case, record in evidence_pairs:
        refs = record.get("references", [])
        ref_entity.append(({str(r.get("stable_entity_key")) for r in refs if r.get("stable_entity_key")}, _gold_entities(case)))
        ref_file.append(({str(r.get("file_path")) for r in refs if r.get("file_path")}, _gold_files(case)))
        gold_ranges = [
            evidence
            for claim in case.get("required_claims", [])
            for evidence in claim.get("evidence_ranges", [])
        ]
        for reference in refs:
            range_checks.append(any(
                reference.get("file_path") == evidence.get("file_path")
                and int(reference.get("start_line", 0)) <= int(evidence.get("end_line", -1))
                and int(reference.get("end_line", -1)) >= int(evidence.get("start_line", 0))
                for evidence in gold_ranges
            ) if gold_ranges else True)
    entity_p, entity_r, *_ = _set_pr(ref_entity)
    file_p, file_r, *_ = _set_pr(ref_file)
    graph_pairs = [
        (cases[str(record["question_id"])], record)
        for record in scored
        if str(record.get("question_id")) in cases
        and cases[str(record["question_id"])].get("source_answerable") is True
        and cases[str(record["question_id"])].get("system_answerable") == "full"
        and all(
            item.get("indexed_in_system") is True
            for item in (
                *cases[str(record["question_id"])].get("gold_nodes", []),
                *cases[str(record["question_id"])].get("gold_edges", []),
            )
        )
        and (_gold_nodes(cases[str(record["question_id"])]) or _gold_edges(cases[str(record["question_id"])]))
    ]
    node_sets = [
        ({str(node.get("stable_entity_key")) for node in record.get("graph_nodes", []) if node.get("stable_entity_key")}, _gold_nodes(case))
        for case, record in graph_pairs
    ]
    edge_sets = [({_edge(edge, True) for edge in record.get("graph_edges", [])}, _gold_edges(case)) for case, record in graph_pairs]
    node_p, node_r, *_ = _set_pr(node_sets)
    edge_p, edge_r, *_ = _set_pr(edge_sets)
    unanswerable = [(cases[str(r["question_id"])], r) for r in scored if cases.get(str(r.get("question_id")), {}).get("source_answerable") is False]
    answerable = [(cases[str(r["question_id"])], r) for r in scored if cases.get(str(r.get("question_id")), {}).get("source_answerable") is True]
    def refused(record: Mapping[str, Any]) -> bool:
        answer = str(record.get("answer", "")).casefold()
        return bool(record.get("uncertainties")) or any(term in answer for term in ("insufficient", "not enough evidence", "无法确定", "证据不足"))
    citation_ok = [r for r in scored if r.get("citation_validation", {}).get("is_valid") is True]
    path_ok = [r for r in scored if not r.get("citation_validation", {}).get("invalid_paths", [])]
    citations = citation_metrics(scored, cases, snapshot_files)
    event_summary = response_event_metrics([
        event for record in scored for event in record.get("llm_response_events", [])
    ])
    change_plan = []
    for record in scored:
        case = cases.get(str(record.get("question_id")))
        if not case or case.get("expected_task_type") != "CHANGE_PLAN":
            continue
        gold = change_plan_file_gold(case)
        predicted = {str(reference.get("file_path")) for reference in record.get("references", []) if reference.get("file_path")}
        change_plan.append((predicted, gold["must_change"] | gold["likely_change"], gold["should_not_change"]))
    cp_precision, cp_recall, *_ = _set_pr((predicted, positive) for predicted, positive, _ in change_plan)
    def repair_summary(population: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        attempted_records = [
            record for record in population
            if any(event.get("phase") == "repair" for event in record.get("llm_response_events", []))
        ]
        succeeded = failed = 0
        for record in attempted_records:
            fallback = (
                record.get("status") != "ok"
                or record.get("guard_failure_inferred") is True
                or "evidence validation repair limit reached" in " ".join(
                    str(item).casefold() for item in record.get("uncertainties", [])
                )
            )
            validation = record.get("citation_validation", {})
            final_passed = not fallback and validation.get("is_valid") is True
            succeeded += int(final_passed)
            failed += int(not final_passed)
        return {
            "population_n": len(population),
            "attempted": len(attempted_records),
            "attempt_rate": _rate(len(attempted_records), len(population)),
            "succeeded": succeeded,
            "failed": failed,
            "outcome_unknown": 0,
            "derivation": "phase_events_plus_final_structured_state",
        }

    run0_repair = repair_summary(scored)
    all_repair = repair_summary(records)
    return {
        "routing": _routing(scored),
        "references": {
            "entity_precision": entity_p, "entity_recall": entity_r,
            "file_precision": file_p, "file_recall": file_r,
            "citation_precision": citations["precision"], "citation_recall": citations["recall"],
            "evidence_range_overlap_rate": _rate(sum(range_checks), len(range_checks)),
        },
        "graph": {"node_precision": node_p, "node_recall": node_r, "edge_precision": edge_p, "edge_recall": edge_r},
        "citation_id_validity_rate": citations.get("citation_id_validity_rate"),
        "citation_validity_rate": citations.get("citation_id_validity_rate"),
        "path_validity_rate": citations["path_validity_rate"],
        "citation_details": citations,
        "refusal": refusal_metrics(scored, cases),
        "change_plan_files": {
            "n": len(change_plan), "positive_precision": cp_precision, "positive_recall": cp_recall,
            "should_not_change_violation_rate": _rate(
                sum(len(predicted & negative) for predicted, _, negative in change_plan),
                sum(len(predicted) for predicted, _, _ in change_plan),
            ),
        },
        "provider": {
            "record_failure_rate": _rate(sum(r.get("status") != "ok" for r in scored), len(scored)),
            "call_deltas": {name: sum(int(r.get("provider_call_deltas", {}).get(name, 0)) for r in scored) for name in ("agent_llm", "query_embedding", "rewrite_llm")},
            "response_events": event_summary,
        },
        "repair": {
            "run0": run0_repair,
            "all_schedule": all_repair,
            "attempt_rate": run0_repair["attempt_rate"],
            "attempts": event_summary["repair_attempts"],
            "succeeded": run0_repair["succeeded"],
            "failed": run0_repair["failed"],
            "outcome_unknown": 0,
            "guard_failure_rate": _rate(sum(bool(r.get("guard_failure_inferred")) for r in scored), len(scored)),
        },
        "latency_seconds_mean": _mean([float(r.get("wall_latency_seconds", 0)) for r in scored]),
        "latency_seconds": latency_summary([float(r.get("wall_latency_seconds", 0)) for r in scored]),
    }


def _jaccard(left: set[Any], right: set[Any]) -> float:
    return 1.0 if not left and not right else len(left & right) / len(left | right)


def _stability(
    records: Sequence[Mapping[str, Any]],
    expected_question_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, dict[int, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        if record.get("variant") == "B5":
            grouped[str(record["question_id"])][int(record["run_index"])] = record
    complete = {qid: runs for qid, runs in grouped.items() if set(runs) >= {0, 1, 2}}
    if expected_question_ids is not None and set(complete) != set(expected_question_ids):
        raise ValueError("stability raw records do not match fixed metadata subset")
    ref_scores: list[float] = []
    node_scores: list[float] = []
    hashes_equal = []
    for runs in complete.values():
        pairs = ((0, 1), (0, 2), (1, 2))
        for left, right in pairs:
            ref_scores.append(_jaccard(
                {r.get("stable_entity_key") for r in runs[left].get("references", [])},
                {r.get("stable_entity_key") for r in runs[right].get("references", [])},
            ))
            node_scores.append(_jaccard(
                {n.get("stable_entity_key") for n in runs[left].get("graph_nodes", [])},
                {n.get("stable_entity_key") for n in runs[right].get("graph_nodes", [])},
            ))
        answer_hashes = {hashlib.sha256(str(run.get("answer", "")).encode()).hexdigest() for run in runs.values() if int(run.get("run_index", -1)) in {0, 1, 2}}
        hashes_equal.append(len(answer_hashes) == 1)
    return {
        "n_questions": len(complete),
        "question_ids": sorted(complete),
        "reference_jaccard_mean": _mean(ref_scores),
        "graph_node_jaccard_mean": _mean(node_scores),
        "answer_hash_agreement_rate": _rate(sum(hashes_equal), len(hashes_equal)),
        "semantic_similarity_evaluated": False,
        "semantic_similarity_status": "not_evaluated",
        "fixed_subset_verified": expected_question_ids is not None,
    }


def _baseline_overall(baseline: Mapping[str, Any], *names: str) -> dict[str, Any]:
    entries = baseline.get("baselines", baseline)
    for name in names:
        if name in entries:
            return dict(entries[name].get("overall", entries[name]))
    return {"status": "not_available"}


def shared_file_baseline(
    name: str,
    records: Sequence[Mapping[str, Any]] | None,
    cases: Mapping[str, Mapping[str, Any]],
    dataset_sha256: str | None,
    repo_commit: str | None,
) -> dict[str, Any]:
    """Recompute baselines on the same indexed must-recall file gold."""
    if not records:
        return {
            "status": "not_comparable",
            "reason": f"{name} raw records were not supplied; aggregated legacy metrics use a different gold contract.",
        }
    schedule_ids = set(cases)
    scored_ids = {
        question_id for question_id, case in cases.items()
        if case.get("source_answerable") is True and _gold_files(case)
    }
    observed_ids: set[str] = set()
    observed_identity: tuple[Any, ...] | None = None
    for record in records:
        question_id = str(record.get("question_id"))
        if (
            not dataset_sha256 or record.get("dataset_sha256") != dataset_sha256
            or not repo_commit or record.get("repo_commit") != repo_commit
        ):
            return {"status": "not_comparable", "reason": f"{name} raw identity is missing or incompatible."}
        identity = tuple(record.get(field) for field in (
            "run_id", "dataset_sha256", "repo_commit", "config_fingerprint",
        ))
        if any(not value for value in identity) or (observed_identity is not None and identity != observed_identity):
            return {"status": "not_comparable", "reason": f"{name} raw identity is missing or incompatible."}
        observed_identity = identity
        if record.get("variant") != name or record.get("run_index") != 0:
            return {"status": "not_comparable", "reason": f"{name} raw variant identity is incompatible."}
        if question_id in observed_ids or question_id not in schedule_ids:
            return {"status": "not_comparable", "reason": f"{name} raw question schedule is incompatible."}
        observed_ids.add(question_id)
    if observed_ids != schedule_ids:
        return {"status": "not_comparable", "reason": f"{name} raw question schedule is incomplete."}
    pairs = [
        (cases[str(record["question_id"])], record)
        for record in records if str(record["question_id"]) in scored_ids
    ]
    return {"status": "comparable", "gold_contract": "indexed_must_recall_files", **_retrieval_summary(pairs, "file", "file_path")}


def retrieval_degeneracy_diagnostics(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Detect when nominally different retrieval variants rank identically."""
    by_variant: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for record in records:
        if record.get("run_index") == 0:
            by_variant[str(record.get("variant"))][str(record.get("question_id"))] = record

    def keys(record: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(
            str(hit.get("stable_entity_key"))
            for hit in record.get("hits", [])[:10]
            if hit.get("stable_entity_key")
        )

    b2_b3_ids = sorted(set(by_variant["B2"]) & set(by_variant["B3"]))
    b2_b3_identical = [
        question_id for question_id in b2_b3_ids
        if keys(by_variant["B2"][question_id]) == keys(by_variant["B3"][question_id])
    ]
    ablation_ids = sorted(
        set(by_variant["A2"]) & set(by_variant["A3"]) & set(by_variant["A4"])
    )
    ablation_identical = [
        question_id for question_id in ablation_ids
        if len({
            keys(by_variant[variant][question_id])
            for variant in ("A2", "A3", "A4")
        }) == 1
    ]
    fully_degenerate = (
        bool(b2_b3_ids) and len(b2_b3_identical) == len(b2_b3_ids)
        and bool(ablation_ids) and len(ablation_identical) == len(ablation_ids)
    )
    return {
        "B2_vs_B3": {
            "n": len(b2_b3_ids),
            "identical_top10_n": len(b2_b3_identical),
            "identical_top10_rate": _rate(len(b2_b3_identical), len(b2_b3_ids)),
        },
        "A2_vs_A3_vs_A4": {
            "n": len(ablation_ids),
            "all_identical_top10_n": len(ablation_identical),
            "all_identical_top10_rate": _rate(len(ablation_identical), len(ablation_ids)),
        },
        "hybrid_comparison_valid": not fully_degenerate,
        "reason": (
            "keyword branch returned zero effective ranking contribution; all compared Top-10 rankings are identical"
            if fully_degenerate else
            "retrieval variants produced distinguishable Top-10 rankings"
        ),
    }


def compute_metrics(
    dataset: Sequence[Mapping[str, Any]],
    retrieval_records: Sequence[Mapping[str, Any]],
    agent_records: Sequence[Mapping[str, Any]],
    baseline_metrics: Mapping[str, Any],
    *,
    retrieval_metadata: Mapping[str, Any] | None = None,
    agent_metadata: Mapping[str, Any] | None = None,
    strict: bool = True,
    dataset_sha256: str | None = None,
    snapshot_files: set[str] | None = None,
    baseline_records: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    retrieval_only: bool = False,
) -> dict[str, Any]:
    selected_dataset = list(dataset)
    if strict:
        if not dataset_sha256:
            raise ValueError("dataset_sha256 is required in formal mode")
        if retrieval_metadata is None or (not retrieval_only and agent_metadata is None):
            raise ValueError("retrieval and agent metadata are required in formal mode")
        selected_dataset = list(validate_formal_artifacts(
            dataset, retrieval_records, agent_records,
            retrieval_metadata, agent_metadata, dataset_sha256,
            retrieval_only=retrieval_only,
        ))
        validate_baseline_identity(baseline_metrics, dataset_sha256)
    cases = {str(case["question_id"]): case for case in selected_dataset}
    retrieval_identity = validate_artifact_identity(retrieval_records)
    agent_identity = validate_artifact_identity(agent_records)
    if retrieval_identity and agent_identity:
        for field in IDENTITY_FIELDS[1:]:
            if retrieval_identity.get(field) != agent_identity.get(field):
                raise ValueError(f"retrieval/agent identity mismatch for {field}")
    shared_identity: dict[str, Any] = {}
    if retrieval_identity or agent_identity:
        source = retrieval_identity or agent_identity
        shared_identity = {
            "dataset_sha256": source.get("dataset_sha256"),
            "repo_commit": source.get("repo_commit"),
            "retrieval_run_id": retrieval_identity.get("run_id"),
            "agent_run_id": agent_identity.get("run_id"),
        }
    retrieval, unanswerable = _retrieval_metrics(cases, retrieval_records)
    source_only = _source_only_diagnostics(cases, retrieval_records, agent_records)
    agent = {} if retrieval_only else {
        variant: _agent_variant(
            cases,
            [r for r in agent_records if r.get("variant") == variant],
            snapshot_files,
        )
        for variant in ("B5", "A8")
    }
    retrieval_latencies = [float(r.get("latency_seconds", 0)) for r in retrieval_records]
    agent_latencies = [float(r.get("wall_latency_seconds", 0)) for r in agent_records]
    all_events = [event for record in agent_records for event in record.get("llm_response_events", [])]
    event_costs = response_event_metrics(all_events)
    return {
        "identity": shared_identity,
        "dataset": {
            "records": len(selected_dataset),
            "source_records": len(dataset),
            "eligibility": "machine_verified_and_accepted",
            "repositories": sorted({str(c.get("repo_id")) for c in selected_dataset if c.get("repo_id")}),
        },
        "environment": {
            "dataset_sha256": dataset_sha256 or shared_identity.get("dataset_sha256"),
            "repo_commit": shared_identity.get("repo_commit") or (retrieval_metadata or {}).get("repo_commit"),
            "retrieval_config": (retrieval_metadata or {}).get("effective_config"),
            "agent_config": (agent_metadata or {}).get("effective_config"),
            "models": event_costs["models"],
            "model_versions": event_costs["model_versions"],
            "os": {"value": platform.platform(), "source": "metrics_process"},
            "cpu": {"value": platform.processor() or "unknown", "source": "metrics_process"},
            "ram": {"value": (agent_metadata or {}).get("environment", {}).get("ram", "unknown"), "source": "agent_metadata_or_unknown"},
            "python": {"value": platform.python_version(), "source": "metrics_process"},
            "node": {"value": (agent_metadata or {}).get("environment", {}).get("node", "unknown"), "source": "agent_metadata_or_unknown"},
            "qdrant_mode": {"value": (retrieval_metadata or {}).get("qdrant_mode", "unknown"), "source": "retrieval_metadata"},
            "providers": {"value": {
                "retrieval": (retrieval_metadata or {}).get("providers", "unknown"),
                "agent": (agent_metadata or {}).get("providers", "unknown"),
            }, "source": "runner_metadata"},
            "scan_measurement": {"value": (retrieval_metadata or {}).get("scan", "unknown"), "source": "retrieval_metadata_or_unknown"},
            "vector_build_measurement": {"value": (retrieval_metadata or {}).get("build", "unknown"), "source": "retrieval_metadata_or_unknown"},
        },
        "baselines": {
            name: shared_file_baseline(
                name,
                (baseline_records or {}).get(name),
                cases,
                dataset_sha256 or shared_identity.get("dataset_sha256"),
                shared_identity.get("repo_commit") or (retrieval_metadata or {}).get("repo_commit"),
            )
            for name in ("B0", "B1")
        },
        "retrieval": retrieval,
        "graph": _graph_metrics(cases, retrieval_records),
        "agent": agent,
        "stability": _stability(
            agent_records,
            (agent_metadata or {}).get("stability_subset", {}).get("question_ids")
            if (agent_metadata or {}).get("stability_subset")
            else None,
        ),
        "diagnostics": {
            "source_unanswerable": unanswerable,
            "source_only": source_only,
            "hybrid_degeneracy": retrieval_degeneracy_diagnostics(retrieval_records),
        },
        "ablations": {
            **{variant: {"status": "executable"} for variant in ("A1", "A2", "A3", "A4", "A5", "A6", "A8")},
            "A7": {"status": "not_executable", "reason": "Canonical Pilot has no multi-turn cases; memory cannot be ablated fairly."},
            "A9": {"status": "not_executable", "reason": "Product services expose no fair validate-without-repair switch."},
        },
        "costs": {
            "provider_counters": {"retrieval": dict((retrieval_metadata or {}).get("provider_counters", {})), "agent": dict((agent_metadata or {}).get("provider_counters", {}))},
            "latency_seconds": {"retrieval_mean": _mean(retrieval_latencies), "agent_mean": _mean(agent_latencies), "retrieval_total": round(sum(retrieval_latencies), 4), "agent_total": round(sum(agent_latencies), 4)},
            "failures": {"retrieval_records": sum(r.get("status") != "ok" for r in retrieval_records), "agent_records": sum(r.get("status") != "ok" for r in agent_records)},
            "response_events": event_costs,
            "usage": {
                "token_usage": "recorded" if event_costs["usage_available_attempts"] else "not_recorded",
                **event_costs["usage"],
                "usage_available_attempts": event_costs["usage_available_attempts"],
                "usage_unavailable_attempts": event_costs["usage_unavailable_attempts"],
            },
            "monetary_cost": {
                "status": "unknown",
                "reason": "Provider pricing was not pinned in evaluation metadata.",
            },
        },
        "methodology": {
            "llm_judge_used": False,
            "semantic_answer_correctness_scored": False,
            "required_claim_coverage_scored": False,
            "hallucination_rate_scored": False,
        },
        "limitations": [
            "single development repository",
            "static analysis is best-effort and may miss runtime or dynamic behavior",
            "semantic answer correctness is not scored without a separately governed judge protocol",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute deterministic Stage 2B metrics")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--retrieval-raw", type=Path, required=True)
    parser.add_argument("--agent-raw", type=Path)
    parser.add_argument("--baseline-metrics", type=Path, required=True)
    parser.add_argument("--b0-raw", type=Path)
    parser.add_argument("--b1-raw", type=Path)
    parser.add_argument("--b0-metadata", type=Path)
    parser.add_argument("--b1-metadata", type=Path)
    parser.add_argument("--retrieval-metadata", type=Path, required=True)
    parser.add_argument("--agent-metadata", type=Path)
    parser.add_argument("--snapshot-code-files", type=Path, required=True)
    parser.add_argument("--snapshot-attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="formally validate and score a selected direct-retrieval schedule without agent artifacts",
    )
    return parser


def validate_metrics_mode_args(args: argparse.Namespace) -> None:
    has_agent_raw = args.agent_raw is not None
    has_agent_metadata = args.agent_metadata is not None
    if has_agent_raw != has_agent_metadata:
        raise ValueError("agent raw and metadata paths must be supplied together")
    if args.retrieval_only:
        if has_agent_raw:
            raise ValueError("retrieval-only mode does not accept agent raw or metadata")
    elif not has_agent_raw:
        raise ValueError("agent raw and metadata are required outside retrieval-only mode")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_metrics_mode_args(args)
    validate_baseline_cli_pair("B0", args.b0_raw, args.b0_metadata)
    validate_baseline_cli_pair("B1", args.b1_raw, args.b1_metadata)
    dataset_bytes = args.dataset.read_bytes()
    dataset_sha = hashlib.sha256(dataset_bytes).hexdigest()
    dataset = load_jsonl(args.dataset)
    retrieval_raw = load_jsonl(args.retrieval_raw)
    agent_raw = load_jsonl(args.agent_raw) if args.agent_raw else []
    retrieval_identity = validate_artifact_identity(retrieval_raw)
    agent_identity = validate_artifact_identity(agent_raw)
    for identity in (retrieval_identity, agent_identity):
        if identity and identity.get("dataset_sha256") != dataset_sha:
            raise ValueError("raw artifact dataset identity does not match dataset file")
    baseline = json.loads(args.baseline_metrics.read_text(encoding="utf-8"))
    validate_baseline_identity(baseline, dataset_sha)
    retrieval_metadata = json.loads(args.retrieval_metadata.read_text(encoding="utf-8")) if args.retrieval_metadata else None
    agent_metadata = json.loads(args.agent_metadata.read_text(encoding="utf-8")) if args.agent_metadata else None
    attestation = validate_snapshot_attestation(
        args.snapshot_attestation, retrieval_metadata, agent_metadata,
    )
    bound_code_files = (
        args.snapshot_attestation.parent
        / str(attestation["artifacts"]["code_files.json"]["path"])
    ).resolve()
    if args.snapshot_code_files.resolve() != bound_code_files:
        raise ValueError("supplied snapshot code_files does not match v3 attestation")
    snapshot_rows = json.loads(args.snapshot_code_files.read_text(encoding="utf-8"))
    if not isinstance(snapshot_rows, list) or any(not isinstance(row, Mapping) or not row.get("file_path") for row in snapshot_rows):
        raise ValueError("snapshot code_files must be a JSON list with file_path on every row")
    snapshot_files = {str(row["file_path"]) for row in snapshot_rows}
    if retrieval_metadata and retrieval_identity and retrieval_metadata.get("run_id") != retrieval_identity.get("run_id"):
        raise ValueError("retrieval metadata run identity mismatch")
    if agent_metadata and agent_identity and agent_metadata.get("run_id") != agent_identity.get("run_id"):
        raise ValueError("agent metadata run identity mismatch")
    baseline_records = {
        "B0": load_jsonl(args.b0_raw) if args.b0_raw else [],
        "B1": load_jsonl(args.b1_raw) if args.b1_raw else [],
    }
    expected_question_ids = {str(case["question_id"]) for case in canonical_cases(dataset)}
    repo_commit = str((retrieval_metadata or {}).get("repo_commit", ""))
    for name, metadata_path in (("B0", args.b0_metadata), ("B1", args.b1_metadata)):
        if metadata_path is not None:
            validate_baseline_artifact(
                name,
                baseline_records[name],
                json.loads(metadata_path.read_text(encoding="utf-8")),
                expected_question_ids,
                dataset_sha,
                repo_commit,
            )
    metrics = compute_metrics(
        dataset,
        retrieval_raw,
        agent_raw,
        baseline,
        retrieval_metadata=retrieval_metadata,
        agent_metadata=agent_metadata,
        strict=True,
        dataset_sha256=dataset_sha,
        snapshot_files=snapshot_files,
        baseline_records=baseline_records,
        retrieval_only=args.retrieval_only,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
