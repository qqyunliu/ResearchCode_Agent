"""B1 baseline: SQLite keyword search for evaluation retrieval layer.

This script implements the B1 baseline described in the evaluation SPEC.
It uses ResearchCode-Agent's actual ``KeywordSearchService`` but WITHOUT
vector search or LLM query rewriting.

Workflow:
  1. Create an isolated SQLite database.
  2. Register the target repository as a project.
  3. Scan the repository using ``IndexService`` (which invokes the real
     parsers and relation builders).
  4. Run ``KeywordSearchService.search()`` for each retrieval-layer question.
  5. Save raw hits as JSONL.

Usage:
    python baseline_keyword.py --repo REPO_PATH --dataset DATASET_PATH \\
                               --db DB_PATH --output OUTPUT_PATH [--top-k 10]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from stage2b_common import sanitize_error_message
from baseline_contract import (
    build_identity,
    default_metadata_path,
    verify_dataset_sha,
    verify_repo_commit,
    write_completed_artifacts,
)

# ---------------------------------------------------------------------------
# Bootstrap: ensure the backend package is importable and the database URL
# points to our isolated DB before any backend module is loaded.
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
_BACKEND_DIR_STR = str(_BACKEND_DIR)
if _BACKEND_DIR_STR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR_STR)


def _configure_backend(db_path: Path) -> None:
    """Set environment so that ``get_settings()`` picks up our DB path.

    Must be called **before** importing ``app.core.config`` because
    ``get_settings`` is ``@lru_cache``-decorated.
    """
    db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    os.environ["RCA_DATABASE_URL"] = db_url
    # Also set a generous source-byte limit so large repos are not truncated.
    os.environ.setdefault("RCA_MAX_SOURCE_BYTES", str(10 * 1024 * 1024))


# ---------------------------------------------------------------------------
# Late imports (after _configure_backend is called)
# ---------------------------------------------------------------------------


def _import_backend():
    """Import backend modules after environment is configured.

    We pre-populate ``sys.modules["app.services"]`` with a stub to prevent
    the real ``app/services/__init__.py`` from running, which has a circular
    import chain (TraceService -> schemas.agent -> agent.__init__ -> executor
    -> schemas.agent).  We only need ``IndexService`` and
    ``KeywordSearchService``, neither of which depends on TraceService.
    """
    import importlib
    import types as pytypes

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base, Project
    from app.models.base import utc_now

    # Stub out app.services.__init__ to avoid circular imports.
    if "app.services" not in sys.modules:
        stub = pytypes.ModuleType("app.services")
        stub.__path__ = [str(_BACKEND_DIR / "app" / "services")]
        stub.__package__ = "app.services"
        sys.modules["app.services"] = stub

    index_mod = importlib.import_module("app.services.index_service")
    IndexService = index_mod.IndexService

    keyword_mod = importlib.import_module("app.retrieval.keyword_search")
    KeywordSearchService = keyword_mod.KeywordSearchService

    return (
        create_engine,
        sessionmaker,
        Base,
        Project,
        utc_now,
        IndexService,
        KeywordSearchService,
    )


# ---------------------------------------------------------------------------
# Dataset helpers (shared with baseline_rg)
# ---------------------------------------------------------------------------


def load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load a dataset from a JSON array file or JSONL file."""
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if stripped.startswith("["):
        return json.loads(stripped)
    return [
        json.loads(line)
        for line in stripped.splitlines()
        if line.strip()
    ]


def filter_retrieval_questions(
    dataset: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only cases whose evaluation_layers include 'retrieval'."""
    return [
        case
        for case in dataset
        if "retrieval" in case.get("evaluation_layers", [])
    ]


# ---------------------------------------------------------------------------
# Token extraction (same as baseline_rg for consistency)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def extract_tokens(query: str, min_length: int = 3) -> list[str]:
    """Extract search tokens from a query string."""
    raw_tokens = _TOKEN_RE.split(query.lower())
    return [t for t in raw_tokens if len(t) >= min_length]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def setup_database(db_path: Path, repo_path: Path):
    """Create DB tables, register the project, and scan.

    Returns ``(session, project_id, scan_summary)``.
    """
    (
        create_engine,
        sessionmaker,
        Base,
        Project,
        utc_now,
        IndexService,
        _,
    ) = _import_backend()

    db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    # Register the project.
    repo_abs = repo_path.resolve()
    project = Project(
        name=repo_abs.name,
        root_path=str(repo_abs),
        status="created",
    )
    session.add(project)
    session.commit()
    project_id = project.id

    # Scan the project.
    index_service = IndexService(session)
    scan_summary = index_service.scan_project(project_id)

    return session, project_id, scan_summary


def run_keyword_search(
    session,
    project_id: int,
    questions: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Run keyword search for each question and return result records.

    Extracts tokens from each question and searches for each token
    individually, then aggregates hits by file_path.  This is necessary
    because KeywordSearchService uses LIKE '%query%' matching, which only
    works for short queries (entity names, identifiers), not full natural
    language sentences.
    """
    (_, _, _, _, _, _, KeywordSearchService) = _import_backend()

    service = KeywordSearchService(session)
    results: list[dict[str, Any]] = []

    for case in questions:
        question_id = case["question_id"]
        question_text = case["question"]
        tokens = extract_tokens(question_text)

        t0 = time.perf_counter()
        error = None
        # Aggregate hits by file_path across all token searches.
        file_hits: dict[str, dict[str, Any]] = {}

        for token in tokens:
            try:
                token_hits = service.search(project_id, token, top_k * 3)
            except Exception as exc:
                error = sanitize_error_message(exc)
                token_hits = []

            for hit in token_hits:
                fp = hit.file_path
                if fp not in file_hits:
                    file_hits[fp] = {
                        "file_path": fp,
                        "entity_type": hit.entity_type,
                        "name": hit.name,
                        "qualified_name": hit.qualified_name,
                        "start_line": hit.start_line,
                        "end_line": hit.end_line,
                        "score": hit.score,
                        "source": hit.source,
                        "matched_tokens": [token],
                    }
                else:
                    existing = file_hits[fp]
                    existing["score"] = max(existing["score"], hit.score)
                    if token not in existing["matched_tokens"]:
                        existing["matched_tokens"].append(token)

        elapsed = time.perf_counter() - t0

        # Rank by number of matched tokens (descending), then score.
        ranked = sorted(
            file_hits.values(),
            key=lambda h: (-len(h["matched_tokens"]), -h["score"], h["file_path"]),
        )

        hit_records = []
        for hit in ranked[:top_k]:
            hit_records.append(
                {
                    "entity_key": f"{hit['entity_type']}:{hit['file_path']}:"
                    f"{hit['qualified_name']}:{hit['start_line']}",
                    "entity_type": hit["entity_type"],
                    "name": hit["name"],
                    "qualified_name": hit["qualified_name"],
                    "file_path": hit["file_path"],
                    "start_line": hit["start_line"],
                    "end_line": hit["end_line"],
                    "score": hit["score"],
                    "source": hit["source"],
                    "matched_tokens": hit["matched_tokens"],
                }
            )

        record: dict[str, Any] = {
            "question_id": question_id,
            "query": question_text,
            "query_tokens": tokens,
            "hits": hit_records,
            "total_hits": len(file_hits),
            "execution_time_seconds": round(elapsed, 4),
        }
        if error is not None:
            record["error"] = error
        results.append(record)

    return results


def run_baseline(
    repo: Path,
    dataset_path: Path,
    db_path: Path,
    output_path: Path,
    top_k: int,
    *,
    dataset_sha256: str | None = None,
    repo_commit: str | None = None,
    metadata_path: Path | None = None,
) -> None:
    """Execute the B1 baseline and write JSONL results."""
    dataset_sha256 = verify_dataset_sha(dataset_path, dataset_sha256)
    repo_commit = verify_repo_commit(repo, repo_commit)
    identity = build_identity("B1", dataset_sha256, repo_commit, top_k)
    _configure_backend(db_path)

    dataset = load_dataset(dataset_path)
    questions = filter_retrieval_questions(dataset)

    # Set up the database and scan the project.
    t_scan_start = time.perf_counter()
    session, project_id, scan_summary = setup_database(db_path, repo)
    t_scan_elapsed = time.perf_counter() - t_scan_start

    entity_count = scan_summary.entities_indexed

    # Run keyword search.
    results = run_keyword_search(session, project_id, questions, top_k)

    for record in results:
        record.update({key: identity[key] for key in (
            "run_id", "dataset_sha256", "repo_commit", "config_fingerprint",
            "variant", "run_index",
        )})
        record["scan_time_seconds"] = round(t_scan_elapsed, 4)
        record["entity_count"] = entity_count
        record["files_indexed"] = scan_summary.files_indexed
        record["project_id"] = project_id

    write_completed_artifacts(
        output_path,
        metadata_path or default_metadata_path(output_path),
        results,
        identity,
        {"scan_time_seconds": round(t_scan_elapsed, 4),
         "entity_count": entity_count, "files_indexed": scan_summary.files_indexed},
    )

    session.close()

    print(
        f"B1 baseline complete: {len(questions)} questions, "
        f"scan={t_scan_elapsed:.2f}s, entities={entity_count}, "
        f"results written to {output_path}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "B1 baseline: SQLite keyword search for evaluation retrieval. "
            "Uses ResearchCode-Agent's KeywordSearchService against an "
            "isolated SQLite database populated by scanning the repository."
        ),
    )
    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        help="Path to the repository root to index and search.",
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="Path to the evaluation dataset (JSON array or JSONL).",
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="Path for the isolated SQLite database (created if needed).",
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
        help="Maximum number of hits to return per question (default: 10).",
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

    db_path: Path = args.db
    if db_path.exists():
        print(
            f"Warning: DB file already exists, will be overwritten: {db_path}",
            file=sys.stderr,
        )
        db_path.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        run_baseline(
            repo, dataset_path, db_path, args.output, args.top_k,
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
