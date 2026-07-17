from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest


SCHEDULE = ("B2", "W60", "W65", "W70", "W75", "W80", "W85", "W90", "W95")


def _case(index: int) -> dict:
    answerable = index < 27
    return {
        "dataset_version": "1.4",
        "question_id": f"q{index:02d}",
        "repo_id": "repo",
        "commit_sha": "a" * 40,
        "task_type": ("CODE_QA", "TRACE_CHAIN", "CHANGE_PLAN")[index % 3],
        "language": ("zh", "en")[index % 2],
        "difficulty": ("easy", "medium", "hard")[index % 3],
        "source_answerable": answerable,
        "gold_status": "machine_verified",
        "execution_status": "executable",
        "evaluation_layers": ["retrieval"],
        "annotation": {"review_status": "accepted"},
        "gold_entities": ([{
            "stable_entity_key": f"e{index}",
            "file_path": f"f{index}.java",
            "indexed_in_system": True,
            "relevance": "must_recall",
        }] if answerable else []),
    }


def _variant_config(name: str) -> dict:
    if name == "B2":
        vector_weight, keyword_weight, mode = 0.7, 0.3, "vector"
    else:
        vector_weight = int(name[1:]) / 100
        keyword_weight, mode = 1 - vector_weight, "hybrid"
    return {
        "mode": mode,
        "rewrite": True,
        "vector_weight": vector_weight,
        "keyword_weight": keyword_weight,
        "fusion": "weighted",
        "graph_depth": None,
    }


def _raw_and_metadata() -> tuple[list[dict], dict]:
    from baseline_contract import config_fingerprint

    records = []
    effective_config = {
        "embedding_provider": "api", "embedding_model": "m", "embedding_dimensions": 8,
        "embedding_endpoint": "https://embed", "rewrite_llm_model": "r",
        "rewrite_llm_endpoint": "https://rewrite", "chunk_max_content_chars": 4000,
        "top_k": 10, "candidate_limit": 20, "lexical_implementation_version": "v2",
        "selected_variants": list(SCHEDULE),
        "variants": {name: _variant_config(name) for name in SCHEDULE},
    }
    identity = {
        "run_id": "weight-run",
        "dataset_sha256": "b" * 64,
        "repo_commit": "a" * 40,
        "config_fingerprint": config_fingerprint(effective_config),
        "db_sha256": "d" * 64,
        "snapshot_sha256": "e" * 64,
    }
    for case_index in range(36):
        for name in SCHEDULE:
            hit_rank = 1
            if name in {"W60", "W65"} and case_index == 0:
                hit_rank = 6
            if name in {"W70", "W75"} and case_index == 0:
                hit_rank = 5
            hits = [
                {"stable_entity_key": f"junk-{case_index}-{rank}", "file_path": f"junk-{rank}.java"}
                for rank in range(1, hit_rank)
            ]
            if case_index < 27:
                hits.append({"stable_entity_key": f"e{case_index}", "file_path": f"f{case_index}.java"})
            record = {
                **identity,
                "question_id": f"q{case_index:02d}",
                "variant": name,
                "run_index": 0,
                "status": "ok",
                "variant_config": _variant_config(name),
                "hits": hits,
            }
            if name != "B2":
                record["branch_diagnostics"] = {
                    "vector_candidate_count": 20,
                    "keyword_candidate_count": 20,
                    "overlap_count": 5,
                    "keyword_only_count": 15,
                    "top10_changed_from_vector": True,
                }
            records.append(record)
    counters = {
        name: {"calls": 1, "successes": 1, "failures": 0, "pending": 0, "unconfirmed": 0}
        for name in ("embedding_sdk_create_attempts", "rewrite_llm_sdk_create_attempts")
    }
    ledgers = {
        name: {"pending": 0, "unconfirmed": 0, "orphan": 0}
        for name in counters
    }
    metadata = {
        **identity,
        "status": "completed",
        "records_written": 324,
        "selected_variants": list(SCHEDULE),
        "provider_counters": counters,
        "provider_ledger_summary": ledgers,
        "effective_config": effective_config,
    }
    return records, metadata


def test_formal_sweep_computes_fractional_file_recall_and_selects_strict_improvement() -> None:
    from compute_fusion_weight_sweep import compute_weight_sweep

    records, metadata = _raw_and_metadata()
    report = compute_weight_sweep([_case(i) for i in range(36)], records, metadata)

    assert report["eligibility"]["eligible_n"] == 27
    # The formal Stage 2B metric contract rounds aggregate means to four places.
    assert report["grid"]["W70"]["file"]["recall@5"] == 1.0
    assert report["grid"]["W75"]["file"]["recall@5"] == 1.0
    assert report["grid"]["W75"]["variant_config"] == _variant_config("W75")
    # W75 fixes Recall@5, while W80 additionally promotes the hit from rank 5
    # to rank 1, so the frozen Recall@5-then-MRR ordering selects W80.
    assert report["selected"]["variant"] == "W80"
    assert report["per_case"]["q00"]["W70"] == {
        "first_correct_rank": 5,
        "recall@5": 1.0,
        "recall@10": 1.0,
    }
    assert set(report["groups"]) == {"language", "task_type", "difficulty"}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw, meta: raw.pop(), "schedule"),
        (lambda raw, meta: raw[1].__setitem__("variant_config", _variant_config("W95")), "variant_config"),
        (lambda raw, meta: raw[1]["branch_diagnostics"].pop("overlap_count"), "branch_diagnostics"),
        (lambda raw, meta: meta["provider_counters"]["embedding_sdk_create_attempts"].__setitem__("pending", 1), "pending"),
        (lambda raw, meta: meta["provider_counters"]["embedding_sdk_create_attempts"].__setitem__("failures", 1), "failures"),
        (lambda raw, meta: meta["provider_counters"]["embedding_sdk_create_attempts"].pop("calls"), "calls"),
        (lambda raw, meta: meta["provider_counters"]["embedding_sdk_create_attempts"].__setitem__("calls", 2), "calls"),
        (lambda raw, meta: raw[0].__setitem__("run_index", False), "run_index"),
        (lambda raw, meta: raw[0].__setitem__("run_index", True), "run_index"),
        (lambda raw, meta: meta.__setitem__("selected_variants", list(reversed(SCHEDULE))), "selected_variants"),
    ],
)
def test_corrupt_formal_artifacts_are_rejected(mutate, message: str) -> None:
    from compute_fusion_weight_sweep import compute_weight_sweep

    records, metadata = _raw_and_metadata()
    mutate(records, metadata)
    with pytest.raises(ValueError, match=message):
        compute_weight_sweep([_case(i) for i in range(36)], records, metadata)


def test_selector_rejects_overall_gain_that_harms_a_language_subgroup() -> None:
    from compute_fusion_weight_sweep import select_weight

    def metrics(r5: float, mrr: float) -> dict:
        return {"file": {"recall@1": r5, "recall@5": r5, "recall@10": 1.0, "mrr": mrr}}

    grid = {"B2": metrics(.8, .8), "W70": metrics(.8, .8), "W75": metrics(.9, .9)}
    groups = {
        "language": {
            "zh": {"W70": metrics(.8, .8), "W75": metrics(.7, .9)},
            "en": {"W70": metrics(.8, .8), "W75": metrics(1.0, .9)},
        },
        "task_type": {"CODE_QA": {"W70": metrics(.8, .8), "W75": metrics(.9, .9)}},
    }

    selection = select_weight(grid, groups, candidates=("W75",))

    assert selection["variant"] is None
    assert any("language:zh" in reason for reason in selection["reasons"]["W75"])


def test_absolute_run_gate_rejects_relative_winner_when_reference_floors_regress() -> None:
    from compute_fusion_weight_sweep import select_weight

    def metrics(value: float) -> dict:
        return {"file": {"recall@1": value, "recall@5": value, "recall@10": value, "mrr": value}}

    grid = {"B2": metrics(.5), "W70": metrics(.5), "W75": metrics(.6)}
    groups = {
        "language": {"en": {"W70": metrics(.5), "W75": metrics(.6)}},
        "task_type": {"CODE_QA": {"W70": metrics(.5), "W75": metrics(.6)}},
    }
    result = select_weight(grid, groups, candidates=("W75",))
    assert result["variant"] is None
    assert result["run_gate"]["passed"] is False


def test_leave_one_out_does_not_apply_full_dataset_absolute_floors() -> None:
    from compute_fusion_weight_sweep import _leave_one_out

    dataset = [_case(i) for i in range(36)]
    dataset[0]["gold_entities"].append({
        "stable_entity_key": "e0-second", "file_path": "f0-second.java",
        "indexed_in_system": True, "relevance": "must_recall",
    })
    records, _ = _raw_and_metadata()
    by_key = {(record["question_id"], record["variant"]): record for record in records}
    eligible = dataset[:27]

    result = _leave_one_out(eligible, by_key)

    assert sum(result["winner_counts"].values()) + result["no_winner_count"] == 27
    assert result["no_winner_count"] < 26
    assert result["absolute_run_gate_enforced"] is False
    assert "denominator" in result["note"]


@pytest.mark.parametrize("field", ["candidate_limit", "embedding_model", "lexical_implementation_version"])
def test_frozen_reference_config_rejects_drift(tmp_path: Path, field: str) -> None:
    from baseline_contract import config_fingerprint
    from compute_fusion_weight_sweep import validate_frozen_identity

    records, metadata = _raw_and_metadata()
    reference = copy.deepcopy(metadata)
    metadata["effective_config"][field] = "drift" if field != "candidate_limit" else 99
    metadata["config_fingerprint"] = config_fingerprint(metadata["effective_config"])
    with pytest.raises(ValueError, match=field):
        validate_frozen_identity(metadata, records, reference, enforce_constants=False)


def test_frozen_identity_rejects_missing_config_and_forged_fingerprint() -> None:
    from compute_fusion_weight_sweep import validate_frozen_identity

    records, metadata = _raw_and_metadata()
    reference = copy.deepcopy(metadata)
    missing = copy.deepcopy(metadata)
    missing.pop("effective_config")
    with pytest.raises(ValueError, match="effective_config"):
        validate_frozen_identity(missing, records, reference, enforce_constants=False)
    forged = copy.deepcopy(metadata)
    forged["config_fingerprint"] = "f" * 64
    for record in records:
        record["config_fingerprint"] = "f" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        validate_frozen_identity(forged, records, reference, enforce_constants=False)


def test_frozen_identity_rejects_noncanonical_commit() -> None:
    from compute_fusion_weight_sweep import FROZEN_DATASET_SHA256, validate_frozen_identity

    records, metadata = _raw_and_metadata()
    metadata["dataset_sha256"] = FROZEN_DATASET_SHA256
    metadata["repo_commit"] = "b" * 40
    for record in records:
        record.update(dataset_sha256=FROZEN_DATASET_SHA256, repo_commit="b" * 40)
    reference = copy.deepcopy(metadata)
    with pytest.raises(ValueError, match="commit"):
        validate_frozen_identity(metadata, records, reference)


@pytest.mark.parametrize("field", ["db_sha256", "snapshot_sha256"])
def test_frozen_identity_rejects_reference_storage_drift(field: str) -> None:
    from compute_fusion_weight_sweep import validate_frozen_identity

    records, metadata = _raw_and_metadata()
    reference = copy.deepcopy(metadata)
    reference[field] = "9" * 64
    with pytest.raises(ValueError, match=field):
        validate_frozen_identity(metadata, records, reference, enforce_constants=False)


def test_per_case_recall_is_fractional_for_multiple_must_recall_files() -> None:
    from compute_fusion_weight_sweep import compute_weight_sweep

    dataset = [_case(i) for i in range(36)]
    dataset[2]["gold_entities"].append({
        "stable_entity_key": "e2-second",
        "file_path": "f2-second.java",
        "indexed_in_system": True,
        "relevance": "must_recall",
    })
    records, metadata = _raw_and_metadata()

    report = compute_weight_sweep(dataset, records, metadata)

    assert report["per_case"]["q02"]["W70"]["recall@5"] == 0.5
    assert report["per_case"]["q02"]["W70"]["recall@10"] == 0.5


def test_dataset_file_hash_must_match_metadata(tmp_path: Path) -> None:
    from compute_fusion_weight_sweep import validate_dataset_file_hash

    dataset = tmp_path / "dataset.jsonl"
    dataset.write_bytes(b"canonical bytes\n")
    with pytest.raises(ValueError, match="dataset SHA"):
        validate_dataset_file_hash(dataset, {"dataset_sha256": "0" * 64})


def _write_ledgers(root: Path, run_id: str) -> None:
    target = root / run_id
    target.mkdir(parents=True)
    for name in ("embedding", "rewrite_llm"):
        (target / f"{name}.jsonl").write_text(
            json.dumps({"event": "started", "attempt_id": f"{name}-1"}) + "\n"
            + json.dumps({"event": "finished", "attempt_id": f"{name}-1", "outcome": "success", "latency_seconds": .25}) + "\n",
            encoding="utf-8",
        )


@pytest.mark.parametrize("corruption", ["pending", "tamper", "missing"])
def test_readonly_ledger_validation_rejects_unreconciled_artifacts(tmp_path: Path, corruption: str) -> None:
    from compute_fusion_weight_sweep import validate_provider_ledgers

    records, metadata = _raw_and_metadata()
    ledger_root = tmp_path / "ledgers"
    _write_ledgers(ledger_root, metadata["run_id"])
    for counter in metadata["provider_counters"].values():
        counter.update(calls=1, successes=1, failures=0, latency_seconds=.25)
    if corruption == "pending":
        path = ledger_root / metadata["run_id"] / "embedding.jsonl"
        path.write_text(path.read_text(encoding="utf-8") + json.dumps({"event": "started", "attempt_id": "pending"}) + "\n", encoding="utf-8")
    elif corruption == "tamper":
        path = ledger_root / metadata["run_id"] / "embedding.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace('"latency_seconds": 0.25', '"latency_seconds": 9.0'), encoding="utf-8")
    else:
        (ledger_root / metadata["run_id"] / "rewrite_llm.jsonl").unlink()
    with pytest.raises(ValueError, match="ledger|latency|pending|missing"):
        validate_provider_ledgers(ledger_root, metadata)


@pytest.mark.parametrize("run_id", ["../escape", ".", "..", "C:/absolute"])
def test_ledger_run_id_cannot_escape_root(tmp_path: Path, run_id: str) -> None:
    from compute_fusion_weight_sweep import validate_provider_ledgers

    _, metadata = _raw_and_metadata()
    metadata["run_id"] = run_id
    with pytest.raises(ValueError, match="run_id|ledger root"):
        validate_provider_ledgers(tmp_path / "ledgers", metadata)


def test_atomic_output_rejects_alias_and_preserves_old_file_before_replace(monkeypatch, tmp_path: Path) -> None:
    import compute_fusion_weight_sweep as sweep

    source = tmp_path / "source.json"
    source.write_text("source", encoding="utf-8")
    with pytest.raises(ValueError, match="alias"):
        sweep.atomic_write_report(source, {"new": True}, protected_paths=[source])
    output = tmp_path / "out.json"
    output.write_text("old", encoding="utf-8")
    monkeypatch.setattr(sweep.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("before replace")))
    with pytest.raises(OSError, match="before replace"):
        sweep.atomic_write_report(output, {"new": True}, protected_paths=[source])
    assert output.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".out.json.*.tmp"))


def test_atomic_output_fsyncs_parent_directory_after_replace(monkeypatch, tmp_path: Path) -> None:
    import compute_fusion_weight_sweep as sweep

    calls = []
    monkeypatch.setattr(sweep, "_fsync_parent_directory", lambda path: calls.append(path))
    output = tmp_path / "out.json"
    sweep.atomic_write_report(output, {"ok": True}, protected_paths=[])
    assert calls == [tmp_path]


def test_parent_directory_fsync_uses_directory_descriptor(monkeypatch, tmp_path: Path) -> None:
    import compute_fusion_weight_sweep as sweep

    calls = []
    monkeypatch.setattr(sweep.os, "open", lambda path, flags: calls.append(("open", path, flags)) or 77)
    monkeypatch.setattr(sweep.os, "fsync", lambda descriptor: calls.append(("fsync", descriptor)))
    monkeypatch.setattr(sweep.os, "close", lambda descriptor: calls.append(("close", descriptor)))
    sweep._fsync_parent_directory(tmp_path)
    assert calls[0][0:2] == ("open", tmp_path)
    assert calls[1:] == [("fsync", 77), ("close", 77)]


def test_cli_output_is_byte_reproducible(monkeypatch, tmp_path: Path) -> None:
    import compute_fusion_weight_sweep as sweep

    records, metadata = _raw_and_metadata()
    dataset_path, raw_path, metadata_path = (tmp_path / name for name in ("dataset.jsonl", "raw.jsonl", "meta.json"))
    dataset_path.write_text("\n".join(json.dumps(_case(i)) for i in range(36)) + "\n", encoding="utf-8")
    dataset_sha = __import__("hashlib").sha256(dataset_path.read_bytes()).hexdigest()
    metadata["dataset_sha256"] = dataset_sha
    for record in records:
        record["dataset_sha256"] = dataset_sha
    raw_path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(json.dumps(metadata), encoding="utf-8")
    code_files, attestation = tmp_path / "code_files.json", tmp_path / "attestation.json"
    code_files.write_text("[]", encoding="utf-8")
    code_files_sha = __import__("hashlib").sha256(code_files.read_bytes()).hexdigest()
    attestation.write_text(json.dumps({
        "artifacts": {"code_files.json": {"path": "code_files.json", "sha256": code_files_sha}}
    }), encoding="utf-8")
    monkeypatch.setattr(sweep, "validate_snapshot_attestation", lambda *args: {"schema_version": "3.0.0"})
    monkeypatch.setattr(sweep, "validate_frozen_identity", lambda *args: None)
    monkeypatch.setattr(sweep, "validate_provider_ledgers", lambda *args: {"embedding.jsonl": "1", "rewrite_llm.jsonl": "2"})
    out1, out2 = tmp_path / "one.json", tmp_path / "two.json"
    common = [
        "--dataset", str(dataset_path), "--raw", str(raw_path), "--metadata", str(metadata_path),
        "--reference-metadata", str(reference_path), "--ledger-dir", str(tmp_path / "ledgers"),
        "--snapshot-code-files", str(code_files), "--snapshot-attestation", str(attestation),
    ]

    assert sweep.main([*common, "--output", str(out1)]) == 0
    assert sweep.main([*common, "--output", str(out2)]) == 0
    assert out1.read_bytes() == out2.read_bytes()


@pytest.mark.parametrize("corruption", ["code_files", "attestation_sha", "attestation_commit"])
def test_cli_rejects_tampered_snapshot_bundle(monkeypatch, tmp_path: Path, corruption: str) -> None:
    import compute_fusion_weight_sweep as sweep
    from compute_stage2b_metrics import SNAPSHOT_REQUIRED_EXPORTS, generate_snapshot_attestation

    records, metadata = _raw_and_metadata()
    dataset_path = tmp_path / "dataset.jsonl"
    raw_path, metadata_path, output_path = tmp_path / "raw.jsonl", tmp_path / "meta.json", tmp_path / "out.json"
    dataset_path.write_text("\n".join(json.dumps(_case(i)) for i in range(36)) + "\n", encoding="utf-8")
    dataset_sha = __import__("hashlib").sha256(dataset_path.read_bytes()).hexdigest()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    for name in SNAPSHOT_REQUIRED_EXPORTS:
        payload = {"commit_sha": "a" * 40} if name == "manifest.json" else []
        (snapshot / name).write_text(json.dumps(payload), encoding="utf-8")
    attestation = snapshot / "attestation.v3.json"
    generate_snapshot_attestation(snapshot / "manifest.json", attestation)
    snapshot_sha = __import__("hashlib").sha256((snapshot / "manifest.json").read_bytes()).hexdigest()
    metadata.update(dataset_sha256=dataset_sha, snapshot_sha256=snapshot_sha)
    for record in records:
        record.update(dataset_sha256=dataset_sha, snapshot_sha256=snapshot_sha)
    raw_path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(sweep, "validate_frozen_identity", lambda *args: None)
    monkeypatch.setattr(sweep, "validate_provider_ledgers", lambda *args: {})
    if corruption == "code_files":
        (snapshot / "code_files.json").write_text("[\"tampered\"]", encoding="utf-8")
    else:
        payload = json.loads(attestation.read_text(encoding="utf-8"))
        if corruption == "attestation_sha":
            payload["artifacts"]["code_files.json"]["sha256"] = "0" * 64
        else:
            payload["repo_commit"] = "b" * 40
        attestation.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA|commit"):
        sweep.main([
            "--dataset", str(dataset_path), "--raw", str(raw_path), "--metadata", str(metadata_path),
            "--reference-metadata", str(reference_path), "--ledger-dir", str(tmp_path / "ledgers"),
            "--snapshot-code-files", str(snapshot / "code_files.json"),
            "--snapshot-attestation", str(attestation), "--output", str(output_path),
        ])
