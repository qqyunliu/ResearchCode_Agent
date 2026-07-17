"""Shared, fail-closed artifact contract for the offline B0/B1 baselines."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_dataset_sha(path: Path, expected: str | None = None) -> str:
    actual = sha256_file(path)
    if expected is None:
        return actual
    expected = expected.strip().lower()
    if not _SHA256_RE.fullmatch(expected):
        raise ValueError("dataset SHA must be exactly 64 lowercase hexadecimal characters")
    if actual != expected:
        raise ValueError(f"dataset SHA mismatch: expected {expected}, got {actual}")
    return actual


def verify_repo_commit(repo: Path, expected: str | None = None) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo.resolve()), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if process.returncode != 0:
        raise ValueError("repository commit cannot be verified with git rev-parse HEAD")
    actual = process.stdout.strip().lower()
    if expected is None:
        return actual
    expected = expected.strip().lower()
    if not _COMMIT_RE.fullmatch(expected):
        raise ValueError("repository commit must be exactly 40 lowercase hexadecimal characters")
    if actual != expected:
        raise ValueError(f"repository commit mismatch: expected {expected}, got {actual}")
    return actual


def build_identity(
    variant: str,
    dataset_sha256: str,
    repo_commit: str,
    top_k: int,
) -> dict[str, Any]:
    effective_config = {
        "contract_version": 1,
        "ranking_unit": "file",
        "top_k": top_k,
        "variant": variant,
    }
    fingerprint = config_fingerprint(effective_config)
    run_digest = hashlib.sha256(
        f"{dataset_sha256}:{repo_commit}:{fingerprint}".encode("ascii")
    ).hexdigest()[:16]
    return {
        "run_id": f"stage2b-{variant.lower()}-{run_digest}",
        "dataset_sha256": dataset_sha256,
        "repo_commit": repo_commit,
        "config_fingerprint": fingerprint,
        "variant": variant,
        "run_index": 0,
        "effective_config": effective_config,
    }


def config_fingerprint(effective_config: Mapping[str, Any]) -> str:
    """Return the canonical fingerprint used by both runners and consumers."""
    encoded = json.dumps(
        effective_config, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_completed_artifacts(
    output_path: Path,
    metadata_path: Path,
    records: Sequence[Mapping[str, Any]],
    identity: Mapping[str, Any],
    extra_metadata: Mapping[str, Any] | None = None,
) -> None:
    raw = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    _atomic_write_text(output_path, raw)
    metadata = {
        key: identity[key]
        for key in (
            "run_id", "dataset_sha256", "repo_commit", "config_fingerprint",
            "variant", "run_index", "effective_config",
        )
    }
    metadata.update({"status": "completed", "records_written": len(records)})
    if extra_metadata:
        metadata.update(extra_metadata)
    _atomic_write_text(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def default_metadata_path(output_path: Path) -> Path:
    return output_path.with_suffix(".metadata.json")
