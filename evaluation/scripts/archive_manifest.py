"""Generate archive-manifest.json for the stage2a-draft-invalid archive.

This script reads all files in the archive directory, computes SHA-256 hashes,
and produces a manifest documenting the archived state along with the reasons
the archive was invalidated.

Usage:
    python evaluation/scripts/archive_manifest.py
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths – resolved relative to the repository root (two levels up from this
# script's location: evaluation/scripts/ -> evaluation/ -> repo root).
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
EVAL_DIR = SCRIPT_DIR.parent  # evaluation/
REPO_ROOT = EVAL_DIR.parent   # repository root

ARCHIVE_DIR = EVAL_DIR / "archive" / "stage2a-draft-invalid"
MANIFEST_PATH = ARCHIVE_DIR / "archive-manifest.json"

# ---------------------------------------------------------------------------
# Mapping: archive filename -> original path (relative to repo root)
# This is derived from the directory structure documented in the pilot report
# and the archive copy operation that created the archive directory.
# ---------------------------------------------------------------------------
ORIGINAL_PATH_MAP: dict[str, dict] = {
    "pilot.jsonl": {
        "original_path": "evaluation/datasets/pilot.jsonl",
        "validation_errors": 511,
        "notes": "36/36 records failed schema validation",
    },
    "pilot_candidates.jsonl": {
        "original_path": "evaluation/annotations/proposed/pilot_candidates.jsonl",
        "validation_errors": 0,
        "notes": "Proposed annotations from question_generator_A",
    },
    "pilot_review.jsonl": {
        "original_path": "evaluation/annotations/reviewed/pilot_review.jsonl",
        "validation_errors": 0,
        "notes": "Adversarial reviewer output",
    },
    "generate_questions.py": {
        "original_path": "evaluation/annotations/proposed/generate_questions.py",
        "validation_errors": 0,
        "notes": "Question generation script",
    },
    "pilot-report.md": {
        "original_path": "evaluation/reports/pilot-report.md",
        "validation_errors": 0,
        "notes": "Stage 2A pilot report (now superseded)",
    },
    "b0_rg.jsonl": {
        "original_path": "evaluation/results/raw/b0_rg.jsonl",
        "validation_errors": 0,
        "notes": "B0 ripgrep baseline raw results",
    },
    "b1_keyword.jsonl": {
        "original_path": "evaluation/results/raw/b1_keyword.jsonl",
        "validation_errors": 0,
        "notes": "B1 keyword baseline raw results",
    },
    "baseline_summary.json": {
        "original_path": "evaluation/results/metrics/baseline_summary.json",
        "validation_errors": 0,
        "notes": "Aggregated baseline metrics summary",
    },
}


def sha256_file(filepath: Path) -> str:
    """Compute the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest() -> dict:
    """Scan the archive directory and build the full manifest structure."""
    archived_at = datetime.now(timezone.utc).isoformat()

    files = []
    for entry in sorted(ARCHIVE_DIR.iterdir()):
        # Skip directories and the manifest itself
        if entry.is_dir():
            continue
        if entry.name == "archive-manifest.json":
            continue

        meta = ORIGINAL_PATH_MAP.get(entry.name, {})
        original_path = meta.get(
            "original_path",
            f"evaluation/archive/stage2a-draft-invalid/{entry.name}",
        )
        validation_errors = meta.get("validation_errors", 0)
        notes = meta.get("notes", "")

        file_hash = sha256_file(entry)

        file_record = {
            "original_path": original_path,
            "archive_path": f"evaluation/archive/stage2a-draft-invalid/{entry.name}",
            "sha256": file_hash,
            "size_bytes": entry.stat().st_size,
            "validation_errors": validation_errors,
            "status": "superseded",
        }
        if notes:
            file_record["notes"] = notes

        files.append(file_record)

    manifest = {
        "archive_id": "stage2a-draft-invalid",
        "archived_at": archived_at,
        "reason": (
            "Schema validation failed (511 errors), role separation violated "
            "(question_generator_A = evidence_annotator), metrics used unverified "
            "proposed annotations, pytest exit code 1"
        ),
        "file_count": len(files),
        "files": files,
    }
    return manifest


def main() -> None:
    if not ARCHIVE_DIR.is_dir():
        print(f"ERROR: Archive directory not found: {ARCHIVE_DIR}")
        raise SystemExit(1)

    manifest = build_manifest()

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Manifest written to: {MANIFEST_PATH}")
    print(f"  Archive ID:  {manifest['archive_id']}")
    print(f"  Archived at: {manifest['archived_at']}")
    print(f"  Files:       {manifest['file_count']}")
    for entry in manifest["files"]:
        print(f"    {entry['archive_path']}")
        print(f"      sha256: {entry['sha256']}")
        print(f"      size:   {entry['size_bytes']} bytes")
        print(f"      status: {entry['status']}")


if __name__ == "__main__":
    main()
