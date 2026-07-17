"""B0 baseline: ripgrep (text search) for evaluation retrieval layer.

This script implements the B0 baseline described in the evaluation SPEC.
It does NOT call ResearchCode-Agent APIs. Instead it:
  1. Extracts search tokens from each question (split on whitespace and
     punctuation, keep tokens >= 3 characters).
  2. Runs ripgrep on the repository (falls back to a pure-Python file scan
     when ripgrep is not available).
  3. Ranks files by the number of distinct tokens that match.

Output is JSONL, one record per retrieval-layer question.

Usage:
    python baseline_rg.py --repo REPO_PATH --dataset DATASET_PATH \\
                          --output OUTPUT_PATH [--top-k 10]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from baseline_contract import (
    build_identity,
    default_metadata_path,
    verify_dataset_sha,
    verify_repo_commit,
    write_completed_artifacts,
)


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

# Split on any run of non-alphanumeric characters (works for both CJK and
# Latin scripts because CJK characters are individually "word" characters
# under Python's regex engine with the re.UNICODE flag).
_TOKEN_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def extract_tokens(query: str, min_length: int = 3) -> list[str]:
    """Extract search tokens from a query string.

    The query is lower-cased, split on whitespace and punctuation, and tokens
    shorter than *min_length* are discarded.  CJK characters count as
    individual tokens when they meet the length requirement.
    """
    raw_tokens = _TOKEN_RE.split(query.lower())
    return [t for t in raw_tokens if len(t) >= min_length]


# ---------------------------------------------------------------------------
# File search
# ---------------------------------------------------------------------------

# Languages/extensions we scan (mirrors scanner.EXTENSION_LANGUAGES).
_INCLUDED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".java",
        ".py",
        ".vue",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".sql",
        ".xml",
        ".yml",
        ".yaml",
        ".json",
    }
)

_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".idea",
        ".vscode",
        ".venv",
        ".pytest_tmp",
        ".worktrees",
        "venv",
    }
)


def _iter_source_files(repo: Path) -> list[Path]:
    """Yield source files under *repo*, respecting ignore rules."""
    candidates: list[Path] = []
    for current_root, dir_names, file_names in os.walk(repo, followlinks=False):
        # Prune ignored directories in-place so os.walk skips them.
        dir_names[:] = [d for d in dir_names if d not in _IGNORED_DIRS]
        for fname in file_names:
            fpath = Path(current_root) / fname
            if fpath.suffix.lower() in _INCLUDED_EXTENSIONS:
                candidates.append(fpath)
    return sorted(candidates)


def _has_ripgrep() -> bool:
    """Return True if ``rg`` is on PATH."""
    try:
        subprocess.run(
            ["rg", "--version"],
            capture_output=True,
            check=False,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _search_ripgrep(
    repo: Path,
    tokens: list[str],
) -> dict[str, dict[str, int]]:
    """Run ripgrep once per token and aggregate match counts per file.

    Returns ``{relative_path: {token: count}}``.
    """
    results: dict[str, dict[str, int]] = {}
    for token in tokens:
        try:
            proc = subprocess.run(
                [
                    "rg",
                    "--count-matches",
                    "--ignore-case",
                    "--fixed-strings",
                    "--no-heading",
                    "--with-filename",
                    token,
                    str(repo),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            continue
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            path_part, _, count_part = line.rpartition(":")
            try:
                count = int(count_part)
            except ValueError:
                continue
            rel = os.path.relpath(path_part, repo).replace(os.sep, "/")
            results.setdefault(rel, {})[token] = count
    return results


def _search_fallback(
    repo: Path,
    tokens: list[str],
) -> dict[str, dict[str, int]]:
    """Pure-Python grep fallback when ripgrep is unavailable.

    Returns ``{relative_path: {token: count}}``.
    """
    results: dict[str, dict[str, int]] = {}
    files = _iter_source_files(repo)
    lower_tokens = [t.lower() for t in tokens]
    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        content_lower = content.lower()
        rel = fpath.relative_to(repo).as_posix()
        token_counts: dict[str, int] = {}
        for token in lower_tokens:
            count = content_lower.count(token)
            if count > 0:
                token_counts[token] = count
        if token_counts:
            results[rel] = token_counts
    return results


def search_repo(
    repo: Path,
    tokens: list[str],
) -> list[dict[str, Any]]:
    """Search *repo* for *tokens* and return ranked file hits.

    Each hit dict contains:
      - file_path (str, relative POSIX path)
      - match_count (int, number of distinct tokens matched)
      - token_counts (dict[str, int], per-token raw counts)
      - score (float, match_count / len(tokens) if tokens else 0.0)
    """
    if not tokens:
        return []

    if _has_ripgrep():
        raw = _search_ripgrep(repo, tokens)
    else:
        raw = _search_fallback(repo, tokens)

    hits: list[dict[str, Any]] = []
    total_tokens = len(tokens)
    for rel_path, token_counts in raw.items():
        match_count = len(token_counts)
        hits.append(
            {
                "file_path": rel_path,
                "match_count": match_count,
                "token_counts": token_counts,
                "score": round(match_count / total_tokens, 4)
                if total_tokens
                else 0.0,
            }
        )
    # Sort by score descending, then file_path ascending for stability.
    hits.sort(key=lambda h: (-h["score"], h["file_path"]))
    return hits


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load a dataset from a JSON array file or JSONL file."""
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if stripped.startswith("["):
        return json.loads(stripped)
    # JSONL: one JSON object per non-empty line.
    return [
        json.loads(line)
        for line in stripped.splitlines()
        if line.strip()
    ]


def filter_retrieval_questions(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only cases whose evaluation_layers include 'retrieval'."""
    return [
        case
        for case in dataset
        if "retrieval" in case.get("evaluation_layers", [])
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_baseline(
    repo: Path,
    dataset_path: Path,
    output_path: Path,
    top_k: int,
    *,
    dataset_sha256: str | None = None,
    repo_commit: str | None = None,
    metadata_path: Path | None = None,
) -> None:
    """Execute the B0 baseline and write JSONL results."""
    dataset_sha256 = verify_dataset_sha(dataset_path, dataset_sha256)
    repo_commit = verify_repo_commit(repo, repo_commit)
    identity = build_identity("B0", dataset_sha256, repo_commit, top_k)
    dataset = load_dataset(dataset_path)
    questions = filter_retrieval_questions(dataset)

    records = []
    for case in questions:
        question_id = case["question_id"]
        question_text = case["question"]
        tokens = extract_tokens(question_text)

        t0 = time.perf_counter()
        hits = search_repo(repo, tokens)
        elapsed = time.perf_counter() - t0

        records.append({
            **{key: identity[key] for key in (
                "run_id", "dataset_sha256", "repo_commit", "config_fingerprint",
                "variant", "run_index",
            )},
            "question_id": question_id,
            "query": question_text,
            "query_tokens": tokens,
            "hits": hits[:top_k],
            "total_hits": len(hits),
            "execution_time_seconds": round(elapsed, 4),
        })
    write_completed_artifacts(
        output_path, metadata_path or default_metadata_path(output_path), records, identity
    )

    print(
        f"B0 baseline complete: {len(questions)} questions, "
        f"results written to {output_path}",
        file=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "B0 baseline: ripgrep text search for evaluation retrieval. "
            "Searches the repository for tokens extracted from each question "
            "and ranks files by the number of distinct matching tokens."
        ),
    )
    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        help="Path to the repository root to search.",
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="Path to the evaluation dataset (JSON array or JSONL).",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the JSONL results file.",
    )
    parser.add_argument("--metadata", type=Path, help="Completed-run metadata sidecar path.")
    parser.add_argument("--dataset-sha", required=True, help="Expected SHA-256 of the dataset bytes.")
    parser.add_argument("--repo-commit", required=True, help="Expected 40-character repository HEAD commit.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Maximum number of hits to include per question (default: 10).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo: Path = args.repo
    if not repo.is_dir():
        print(f"Error: repo path is not a directory: {repo}", file=sys.stderr)
        return 1

    dataset_path: Path = args.dataset
    if not dataset_path.is_file():
        print(f"Error: dataset file not found: {dataset_path}", file=sys.stderr)
        return 1

    try:
        run_baseline(
            repo, dataset_path, args.output, args.top_k,
            dataset_sha256=args.dataset_sha,
            repo_commit=args.repo_commit,
            metadata_path=args.metadata,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
