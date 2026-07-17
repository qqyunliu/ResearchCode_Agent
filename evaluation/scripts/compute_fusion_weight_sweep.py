"""Validate and analyse the frozen Stage 2B fusion-weight development sweep."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import math
import os
import random
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
RUNNERS_DIR = SCRIPT_DIR.parent / "runners"
for path in (SCRIPT_DIR, RUNNERS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from compute_stage2b_metrics import (  # noqa: E402
    BRANCH_DIAGNOSTIC_FIELDS,
    RAW_IDENTITY_FIELDS,
    RETRIEVAL_PROVIDER_COUNTERS,
    _gold_files,
    _retrieval_summary,
    canonical_cases,
    load_jsonl,
    validate_snapshot_attestation,
)
from baseline_contract import config_fingerprint  # noqa: E402


SELECTED_VARIANTS = ("B2", "W60", "W65", "W70", "W75", "W80", "W85", "W90", "W95")
WEIGHT_VARIANTS = SELECTED_VARIANTS[1:]
BOOTSTRAP_SEED = 20260717
BOOTSTRAP_ITERATIONS = 10_000
TOLERANCE = 1e-12
FROZEN_DATASET_SHA256 = "86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c"
FROZEN_REPO_COMMIT = "41720e624c5a668c7d3777835e4c87095a7a1dfd"
B2_R10_FLOOR = 0.9815
W70_R5_FLOOR = 0.9722
W70_MRR_FLOOR = 0.8488
FROZEN_CONFIG_KEYS = (
    "embedding_provider", "embedding_model", "embedding_dimensions", "embedding_endpoint",
    "rewrite_llm_model", "rewrite_llm_endpoint", "chunk_max_content_chars", "top_k",
    "candidate_limit", "lexical_implementation_version",
)
_RUN_ID_RE = re.compile(r"[A-Za-z0-9._-]+")


def _expected_variant_config(name: str) -> dict[str, Any]:
    if name == "B2":
        vector_weight, mode = 0.7, "vector"
    else:
        vector_weight, mode = int(name[1:]) / 100, "hybrid"
    return {
        "mode": mode,
        "rewrite": True,
        "vector_weight": vector_weight,
        "keyword_weight": 1 - vector_weight,
        "fusion": "weighted",
        "graph_depth": None,
    }


def _same_config(actual: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(actual, Mapping) or set(actual) != set(expected):
        return False
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if isinstance(expected_value, float):
            if not isinstance(actual_value, (int, float)) or abs(float(actual_value) - expected_value) > TOLERANCE:
                return False
        elif actual_value != expected_value:
            return False
    return True


def _validate_diagnostics(record: Mapping[str, Any], line_number: int) -> None:
    diagnostics = record.get("branch_diagnostics")
    if not isinstance(diagnostics, Mapping) or set(diagnostics) != BRANCH_DIAGNOSTIC_FIELDS:
        raise ValueError(f"branch_diagnostics must contain exactly five fields at line {line_number}")
    counts: dict[str, int] = {}
    for field in ("vector_candidate_count", "keyword_candidate_count", "overlap_count", "keyword_only_count"):
        value = diagnostics.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(f"branch_diagnostics {field} must be a non-negative integer at line {line_number}")
        counts[field] = value
    if type(diagnostics.get("top10_changed_from_vector")) is not bool:
        raise ValueError("branch_diagnostics top10_changed_from_vector must be boolean")
    if counts["overlap_count"] > min(counts["vector_candidate_count"], counts["keyword_candidate_count"]):
        raise ValueError("branch_diagnostics overlap_count is inconsistent")
    if counts["keyword_only_count"] != counts["keyword_candidate_count"] - counts["overlap_count"]:
        raise ValueError("branch_diagnostics keyword_only_count is inconsistent")


def _validate_provider_state(metadata: Mapping[str, Any]) -> None:
    counters = metadata.get("provider_counters")
    ledgers = metadata.get("provider_ledger_summary")
    if not isinstance(counters, Mapping) or set(counters) != set(RETRIEVAL_PROVIDER_COUNTERS):
        raise ValueError("provider_counters must contain exactly the two retrieval providers")
    if not isinstance(ledgers, Mapping) or set(ledgers) != set(RETRIEVAL_PROVIDER_COUNTERS):
        raise ValueError("provider ledger summary must contain exactly the two retrieval providers")
    for provider in RETRIEVAL_PROVIDER_COUNTERS:
        counter, ledger = counters[provider], ledgers[provider]
        if not isinstance(counter, Mapping) or not isinstance(ledger, Mapping):
            raise ValueError(f"{provider} provider state is malformed")
        required = ("calls", "successes", "failures", "pending", "unconfirmed")
        for field in required:
            if type(counter.get(field)) is not int or counter[field] < 0:
                raise ValueError(f"{provider} {field} must be a non-negative integer")
        if counter["failures"] != 0:
            raise ValueError(f"{provider} failures must be zero")
        if counter["pending"] != 0:
            raise ValueError(f"{provider} pending must be zero")
        if counter["unconfirmed"] != 0:
            raise ValueError(f"{provider} unconfirmed must be zero")
        if counter["calls"] != counter["successes"] + counter["failures"]:
            raise ValueError(f"{provider} calls must equal successes plus failures")
        for field in ("pending", "unconfirmed"):
            if type(ledger.get(field)) is not int or ledger[field] != 0:
                raise ValueError(f"{provider} ledger {field} must be zero")
        if type(ledger.get("orphan")) is not int or ledger["orphan"] != 0:
            raise ValueError(f"{provider} ledger orphan must be zero")


def validate_sweep_artifacts(
    dataset: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Fail closed unless dataset, raw schedule, identity, and provider state are exact."""
    canonical = canonical_cases(dataset)
    if len(canonical) != 36:
        raise ValueError(f"weight sweep requires exactly 36 canonical cases, got {len(canonical)}")
    commits = {str(case["commit_sha"]) for case in canonical}
    if commits != {str(metadata.get("repo_commit"))}:
        raise ValueError("dataset/metadata repository commit identity mismatch")
    if metadata.get("status") != "completed":
        raise ValueError("metadata status must be completed")
    if metadata.get("selected_variants") != list(SELECTED_VARIANTS):
        raise ValueError("metadata selected_variants must match the frozen ordered schedule")
    if metadata.get("records_written") != 324 or len(records) != 324:
        raise ValueError("raw schedule must contain exactly 36 x 9 = 324 records")
    for field in RAW_IDENTITY_FIELDS:
        if not metadata.get(field):
            raise ValueError(f"metadata identity field {field} is required")
    _validate_provider_state(metadata)

    question_ids = {str(case["question_id"]) for case in canonical}
    expected = {(question_id, variant, 0) for question_id in question_ids for variant in SELECTED_VARIANTS}
    observed: set[tuple[str, str, int]] = set()
    for line_number, record in enumerate(records, 1):
        for field in RAW_IDENTITY_FIELDS:
            if record.get(field) != metadata[field]:
                raise ValueError(f"raw/metadata identity mismatch for {field} at line {line_number}")
        if record.get("status") != "ok":
            raise ValueError(f"raw status must be ok at line {line_number}")
        run_index = record.get("run_index")
        if type(run_index) is not int or run_index != 0:
            raise ValueError(f"raw run_index must be integer zero at line {line_number}")
        key = (str(record.get("question_id")), str(record.get("variant")), run_index)
        if key in observed:
            raise ValueError(f"duplicate raw schedule key: {key}")
        observed.add(key)
        name = str(record.get("variant"))
        if name not in SELECTED_VARIANTS or not _same_config(record.get("variant_config"), _expected_variant_config(name)):
            raise ValueError(f"variant_config does not match {name} at line {line_number}")
        if name != "B2":
            _validate_diagnostics(record, line_number)
    if observed != expected:
        raise ValueError(f"raw schedule mismatch: expected {len(expected)}, got {len(observed)}")

    eligible = [
        case for case in canonical
        if "retrieval" in case.get("evaluation_layers", [])
        and case.get("source_answerable") is True
        and _gold_files(case)
    ]
    if len(eligible) != 27:
        raise ValueError(f"weight sweep requires exactly 27 indexed must_recall retrieval cases, got {len(eligible)}")
    return canonical, eligible


def validate_dataset_file_hash(path: Path, metadata: Mapping[str, Any]) -> str:
    """Bind the exact dataset bytes supplied to the raw artifact identity."""
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if metadata.get("dataset_sha256") != actual:
        raise ValueError("dataset SHA does not match metadata identity")
    return actual


def validate_frozen_identity(
    metadata: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    reference: Mapping[str, Any],
    *,
    enforce_constants: bool = True,
) -> None:
    """Bind the sweep to the previously reviewed retrieval configuration."""
    for label, item in (("metadata", metadata), ("reference", reference)):
        if item.get("status") != "completed":
            raise ValueError(f"{label} status must be completed")
        config = item.get("effective_config")
        if not isinstance(config, Mapping):
            raise ValueError(f"{label} effective_config is required")
        if config_fingerprint(config) != item.get("config_fingerprint"):
            raise ValueError(f"{label} config fingerprint is forged or stale")
        for field in ("dataset_sha256", "repo_commit", "run_id", "config_fingerprint", "db_sha256", "snapshot_sha256"):
            if not item.get(field):
                raise ValueError(f"{label} identity field {field} is required")
    if enforce_constants:
        for label, item in (("metadata", metadata), ("reference", reference)):
            if item.get("dataset_sha256") != FROZEN_DATASET_SHA256:
                raise ValueError(f"{label} dataset SHA is not the frozen Pilot dataset")
            if str(item.get("repo_commit", "")).lower() != FROZEN_REPO_COMMIT:
                raise ValueError(f"{label} commit is not the frozen Pilot commit")
    current, baseline = metadata["effective_config"], reference["effective_config"]
    for field in ("db_sha256", "snapshot_sha256"):
        if metadata[field] != reference[field]:
            raise ValueError(f"current/reference {field} identity differs")
    for key in FROZEN_CONFIG_KEYS:
        if key not in current or key not in baseline or current[key] != baseline[key]:
            raise ValueError(f"frozen effective_config {key} differs from reference")
    if current.get("selected_variants") != list(SELECTED_VARIANTS):
        raise ValueError("sweep effective_config selected_variants is not frozen")
    variants = current.get("variants")
    if not isinstance(variants, Mapping) or set(variants) != set(SELECTED_VARIANTS):
        raise ValueError("sweep effective_config variants are not the frozen schedule")
    for name in SELECTED_VARIANTS:
        if not _same_config(variants[name], _expected_variant_config(name)):
            raise ValueError(f"sweep effective_config variant {name} is not frozen")
    for record in records:
        if record.get("dataset_sha256") != metadata.get("dataset_sha256") or record.get("repo_commit") != metadata.get("repo_commit"):
            raise ValueError("raw dataset SHA/commit identity differs from metadata")


def _read_ledger(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"provider ledger missing: {path}")
    content = path.read_bytes()
    if content and not content.endswith(b"\n"):
        raise ValueError(f"provider ledger lacks a complete final newline: {path}")
    attempts: dict[str, Mapping[str, Any] | None] = {}
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid provider ledger JSON at {path}:{line_number}") from error
        if not isinstance(event, Mapping) or event.get("event") not in {"started", "finished"}:
            raise ValueError(f"unknown provider ledger event at {path}:{line_number}")
        attempt_id = event.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError(f"provider ledger attempt_id is invalid at {path}:{line_number}")
        if event["event"] == "started":
            if attempt_id in attempts:
                raise ValueError(f"duplicate provider ledger start at {path}:{line_number}")
            attempts[attempt_id] = None
        else:
            if attempt_id not in attempts or attempts[attempt_id] is not None:
                raise ValueError(f"unknown or duplicate provider ledger finish at {path}:{line_number}")
            outcome, latency = event.get("outcome"), event.get("latency_seconds")
            if outcome not in {"success", "failure"} or isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or latency < 0:
                raise ValueError(f"provider ledger outcome/latency is invalid at {path}:{line_number}")
            attempts[attempt_id] = event
    if any(event is None for event in attempts.values()):
        raise ValueError(f"provider ledger has pending attempts: {path}")
    terminal = [event for event in attempts.values() if event is not None]
    return {
        "calls": len(terminal),
        "successes": sum(event["outcome"] == "success" for event in terminal),
        "failures": sum(event["outcome"] == "failure" for event in terminal),
        "latency_seconds": sum(float(event["latency_seconds"]) for event in terminal),
        "pending": 0, "unconfirmed": 0, "orphan": 0,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def validate_provider_ledgers(ledger_dir: Path, metadata: Mapping[str, Any]) -> dict[str, str]:
    run_id = metadata.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id) or run_id in {".", ".."}:
        raise ValueError("provider ledger run_id is invalid")
    ledger_root = ledger_dir.resolve()
    run_root = (ledger_root / run_id).resolve()
    if run_root == ledger_root or ledger_root not in run_root.parents:
        raise ValueError("provider ledger run directory escapes ledger root")
    files = {
        "embedding_sdk_create_attempts": run_root / "embedding.jsonl",
        "rewrite_llm_sdk_create_attempts": run_root / "rewrite_llm.jsonl",
    }
    shas: dict[str, str] = {}
    for provider, path in files.items():
        actual = _read_ledger(path)
        reported = metadata["provider_counters"][provider]
        for field in ("calls", "successes", "failures", "pending", "unconfirmed"):
            if reported.get(field) != actual[field]:
                raise ValueError(f"provider ledger {provider} {field} differs from metadata")
        latency = reported.get("latency_seconds")
        if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isclose(float(latency), actual["latency_seconds"], rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(f"provider ledger {provider} latency differs from metadata")
        summary = metadata["provider_ledger_summary"][provider]
        for field in ("pending", "unconfirmed", "orphan"):
            if summary.get(field) != actual[field]:
                raise ValueError(f"provider ledger summary {provider} {field} differs from ledger")
        shas[path.name] = actual["sha256"]
    return shas


def _paths_alias(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def atomic_write_report(output: Path, payload: Mapping[str, Any], *, protected_paths: Sequence[Path]) -> None:
    if any(_paths_alias(output, path) for path in protected_paths):
        raise ValueError("output path aliases an input, reference, or ledger file")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        assert temporary is not None
        os.replace(temporary, output)
        _fsync_parent_directory(output.parent)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _fsync_parent_directory(path: Path) -> None:
    """Durably persist the rename; Windows does not always permit directory handles."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if os.name == "nt" and error.errno in {errno.EACCES, errno.EINVAL, errno.ENOTSUP, errno.EPERM}:
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if not (os.name == "nt" and error.errno in {errno.EACCES, errno.EINVAL, errno.ENOTSUP, errno.EPERM}):
                raise
    finally:
        os.close(descriptor)


def _variant_metrics(cases: Sequence[Mapping[str, Any]], records_by_key: Mapping[tuple[str, str], Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for variant in SELECTED_VARIANTS:
        pairs = [(case, records_by_key[(str(case["question_id"]), variant)]) for case in cases]
        result[variant] = {
            "variant_config": _expected_variant_config(variant),
            "file": _retrieval_summary(pairs, "file", "file_path"),
        }
    return result


def _group_metrics(
    cases: Sequence[Mapping[str, Any]], records_by_key: Mapping[tuple[str, str], Mapping[str, Any]]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in ("language", "task_type", "difficulty"):
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for case in cases:
            grouped[str(case.get(field))].append(case)
        output[field] = {
            value: _variant_metrics(group, records_by_key)
            for value, group in sorted(grouped.items())
        }
    return output


def select_weight(
    grid: Mapping[str, Mapping[str, Any]],
    groups: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Any]]]],
    *,
    candidates: Sequence[str] = WEIGHT_VARIANTS,
    enforce_absolute_run_gate: bool = True,
) -> dict[str, Any]:
    """Apply the frozen hard gates; never fall back when no weight qualifies."""
    b2, baseline = grid["B2"]["file"], grid["W70"]["file"]
    run_failures = []
    if enforce_absolute_run_gate:
        if b2["recall@10"] + TOLERANCE < B2_R10_FLOOR:
            run_failures.append(f"B2 recall@10 is below frozen floor {B2_R10_FLOOR}")
        if baseline["recall@5"] + TOLERANCE < W70_R5_FLOOR:
            run_failures.append(f"W70 recall@5 is below frozen floor {W70_R5_FLOOR}")
        if baseline["mrr"] + TOLERANCE < W70_MRR_FLOOR:
            run_failures.append(f"W70 MRR is below frozen floor {W70_MRR_FLOOR}")
    reasons: dict[str, list[str]] = {}
    qualified: list[str] = []
    for variant in candidates:
        current = grid[variant]["file"]
        failures: list[str] = []
        if current["recall@10"] + TOLERANCE < b2["recall@10"]:
            failures.append("recall@10 is below B2")
        if current["recall@5"] + TOLERANCE < baseline["recall@5"]:
            failures.append("recall@5 is below W70")
        if enforce_absolute_run_gate and current["recall@10"] + TOLERANCE < B2_R10_FLOOR:
            failures.append("recall@10 is below frozen B2 floor")
        if enforce_absolute_run_gate and current["recall@5"] + TOLERANCE < W70_R5_FLOOR:
            failures.append("recall@5 is below frozen W70 floor")
        if not (
            current["recall@5"] > baseline["recall@5"] + TOLERANCE
            or current["mrr"] > baseline["mrr"] + TOLERANCE
        ):
            failures.append("neither recall@5 nor MRR strictly improves over W70")
        for field in ("language", "task_type"):
            for value, variants in groups.get(field, {}).items():
                if variants[variant]["file"]["recall@5"] + TOLERANCE < variants["W70"]["file"]["recall@5"]:
                    failures.append(f"{field}:{value} recall@5 is below W70")
        reasons[variant] = failures
        if not failures and not run_failures:
            qualified.append(variant)
    winner = min(
        qualified,
        key=lambda variant: (
            -grid[variant]["file"]["recall@5"],
            -grid[variant]["file"]["mrr"],
            -grid[variant]["file"]["recall@1"],
            abs(int(variant[1:]) / 100 - 0.7),
            int(variant[1:]) / 100,
        ),
        default=None,
    )
    return {
        "variant": winner,
        "vector_weight": None if winner is None else int(winner[1:]) / 100,
        "keyword_weight": None if winner is None else 1 - int(winner[1:]) / 100,
        "qualified": qualified,
        "reasons": reasons,
        "run_gate": {
            "absolute_floors_enforced": enforce_absolute_run_gate,
            "passed": not run_failures,
            "reasons": run_failures,
        },
    }


def _per_case_metrics(
    cases: Sequence[Mapping[str, Any]], records_by_key: Mapping[tuple[str, str], Mapping[str, Any]]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for case in cases:
        question_id = str(case["question_id"])
        gold = _gold_files(case)
        output[question_id] = {}
        for variant in SELECTED_VARIANTS:
            predicted = list(dict.fromkeys(
                str(hit["file_path"])
                for hit in records_by_key[(question_id, variant)].get("hits", [])
                if hit.get("file_path")
            ))
            rank = next((position for position, path in enumerate(predicted, 1) if path in gold), None)
            output[question_id][variant] = {
                "first_correct_rank": rank,
                "recall@5": len(gold & set(predicted[:5])) / len(gold),
                "recall@10": len(gold & set(predicted[:10])) / len(gold),
            }
    return output


def _raw_case_stat(case_metrics: Mapping[str, Any], variant: str, metric: str) -> float:
    if metric == "recall@5":
        return float(case_metrics[variant]["recall@5"])
    rank = case_metrics[variant]["first_correct_rank"]
    return 0.0 if rank is None else 1 / rank


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap(per_case: Mapping[str, Any]) -> dict[str, Any]:
    ids = sorted(per_case)
    rng = random.Random(BOOTSTRAP_SEED)
    accumulators = {
        variant: {"r5_ge": 0, "mrr_ge": 0, "r5_delta": [], "mrr_delta": []}
        for variant in WEIGHT_VARIANTS
    }
    for _ in range(BOOTSTRAP_ITERATIONS):
        sample = [ids[rng.randrange(len(ids))] for _ in ids]
        baseline_r5 = sum(_raw_case_stat(per_case[item], "W70", "recall@5") for item in sample) / len(sample)
        baseline_mrr = sum(_raw_case_stat(per_case[item], "W70", "mrr") for item in sample) / len(sample)
        for variant, values in accumulators.items():
            r5 = sum(_raw_case_stat(per_case[item], variant, "recall@5") for item in sample) / len(sample)
            mrr = sum(_raw_case_stat(per_case[item], variant, "mrr") for item in sample) / len(sample)
            r5_delta, mrr_delta = r5 - baseline_r5, mrr - baseline_mrr
            values["r5_ge"] += int(r5_delta >= -TOLERANCE)
            values["mrr_ge"] += int(mrr_delta >= -TOLERANCE)
            values["r5_delta"].append(r5_delta)
            values["mrr_delta"].append(mrr_delta)
    return {
        "seed": BOOTSTRAP_SEED,
        "iterations": BOOTSTRAP_ITERATIONS,
        "candidates": {
            variant: {
                "bootstrap_frequency_recall@5_ge_W70": values["r5_ge"] / BOOTSTRAP_ITERATIONS,
                "bootstrap_frequency_mrr_ge_W70": values["mrr_ge"] / BOOTSTRAP_ITERATIONS,
                "recall@5_delta_95pct": [_quantile(values["r5_delta"], .025), _quantile(values["r5_delta"], .975)],
                "mrr_delta_95pct": [_quantile(values["mrr_delta"], .025), _quantile(values["mrr_delta"], .975)],
            }
            for variant, values in accumulators.items()
        },
    }


def _leave_one_out(
    cases: Sequence[Mapping[str, Any]], records_by_key: Mapping[tuple[str, str], Mapping[str, Any]]
) -> dict[str, Any]:
    winners: Counter[str] = Counter()
    no_winner = 0
    for omitted in cases:
        subset = [case for case in cases if case is not omitted]
        selection = select_weight(
            _variant_metrics(subset, records_by_key),
            _group_metrics(subset, records_by_key),
            enforce_absolute_run_gate=False,
        )
        if selection["variant"] is None:
            no_winner += 1
        else:
            winners[selection["variant"]] += 1
    return {
        "iterations": len(cases),
        "winner_counts": dict(sorted(winners.items())),
        "no_winner_count": no_winner,
        "absolute_run_gate_enforced": False,
        "note": "Full-run absolute floors are excluded because leave-one-out changes the denominator; subset-relative gates remain enforced.",
    }


def compute_weight_sweep(
    dataset: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    canonical, eligible = validate_sweep_artifacts(dataset, records, metadata)
    by_key = {(str(record["question_id"]), str(record["variant"])): record for record in records}
    grid = _variant_metrics(eligible, by_key)
    groups = _group_metrics(eligible, by_key)
    per_case = _per_case_metrics(eligible, by_key)
    return {
        "schema_version": "1.0.0",
        "artifact_identity": {field: metadata[field] for field in RAW_IDENTITY_FIELDS},
        "schedule": list(SELECTED_VARIANTS),
        "eligibility": {
            "canonical_n": len(canonical),
            "eligible_n": len(eligible),
            "contract": "source_answerable retrieval cases with indexed must_recall file gold",
            "included_question_ids": sorted(str(case["question_id"]) for case in eligible),
            "excluded": {
                str(case["question_id"]): "not a source-answerable retrieval case with indexed must_recall file gold"
                for case in canonical if case not in eligible
            },
        },
        "grid": grid,
        "groups": groups,
        "selected": select_weight(grid, groups),
        "per_case": per_case,
        "robustness": {
            "bootstrap": _bootstrap(per_case),
            "leave_one_case_out": _leave_one_out(eligible, by_key),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--reference-metadata", type=Path, required=True)
    parser.add_argument("--ledger-dir", type=Path, required=True)
    parser.add_argument("--snapshot-code-files", type=Path, required=True)
    parser.add_argument("--snapshot-attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset, records = load_jsonl(args.dataset), load_jsonl(args.raw)
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    reference = json.loads(args.reference_metadata.read_text(encoding="utf-8"))
    validate_dataset_file_hash(args.dataset, metadata)
    validate_frozen_identity(metadata, records, reference)
    ledger_shas = validate_provider_ledgers(args.ledger_dir, metadata)
    validate_snapshot_attestation(args.snapshot_attestation, metadata, None)
    attestation = json.loads(args.snapshot_attestation.read_text(encoding="utf-8"))
    code_files_entry = attestation.get("artifacts", {}).get("code_files.json")
    if (
        args.snapshot_code_files.resolve().parent != args.snapshot_attestation.resolve().parent
        or not isinstance(code_files_entry, Mapping)
        or code_files_entry.get("path") != "code_files.json"
        or code_files_entry.get("sha256") != hashlib.sha256(args.snapshot_code_files.read_bytes()).hexdigest()
    ):
        raise ValueError("snapshot code_files does not match attestation binding")
    report = compute_weight_sweep(dataset, records, metadata)
    report["ledger_sha256"] = ledger_shas
    ledger_files = [
        args.ledger_dir / metadata["run_id"] / "embedding.jsonl",
        args.ledger_dir / metadata["run_id"] / "rewrite_llm.jsonl",
    ]
    atomic_write_report(args.output, report, protected_paths=[
        args.dataset, args.raw, args.metadata, args.reference_metadata,
        args.snapshot_code_files, args.snapshot_attestation, *ledger_files,
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
