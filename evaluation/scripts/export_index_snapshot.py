"""Export an index snapshot from a ResearchCode-Agent SQLite database.

Reads the database created by ``baseline_keyword.py`` (or by the main
application) and writes structured JSON files suitable for offline analysis
and gold-label cross-referencing.

Exports:
  - ``code_files.json``: indexed source files
  - ``code_entities.json``: parsed code entities with stable keys
  - ``code_relations.json``: static relations between entities
  - ``scan_issues.json``: scan warnings and errors
  - ``frontend_diagnostics.json``: frontend API-call matching summary

Usage:
    python export_index_snapshot.py --db DB_PATH --repo-id REPO_ID \\
                                   --commit-sha SHA --output OUTPUT_DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: make the backend package and sibling scripts importable.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR_STR = str(_SCRIPTS_DIR)
if _SCRIPTS_DIR_STR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR_STR)

_BACKEND_DIR = _SCRIPTS_DIR.parent.parent / "backend"
_BACKEND_DIR_STR = str(_BACKEND_DIR)
if _BACKEND_DIR_STR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR_STR)

# Re-use the canonical stable-entity-key implementation that lives in the
# same directory (``stable_entity_key.py``).
from stable_entity_key import compute_stable_key  # noqa: E402


def _configure_backend(db_path: Path) -> None:
    """Set environment so that ``get_settings()`` picks up our DB path."""
    db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    os.environ["RCA_DATABASE_URL"] = db_url


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


def compute_content_hash(content: str) -> str:
    """SHA-256 of the entity content (not the full file)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _stable_entity_key(
    repo_id: str,
    commit_sha: str,
    file_path: str,
    entity_type: str,
    qualified_name: str,
    start_line: int,
    end_line: int,
) -> str:
    """Thin wrapper around the canonical ``compute_stable_key``."""
    return compute_stable_key(
        repo_id=repo_id,
        commit_sha=commit_sha,
        file_path=file_path,
        entity_type=entity_type,
        qualified_name=qualified_name,
        start_line=start_line,
        end_line=end_line,
    )


# ---------------------------------------------------------------------------
# Export logic
# ---------------------------------------------------------------------------


def _import_backend():
    """Import backend modules after environment is configured."""
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import sessionmaker

    from app.models import (
        Base,
        CodeEntity,
        CodeFile,
        CodeRelation,
        Project,
        ScanIssue,
    )

    return (
        create_engine,
        sessionmaker,
        select,
        func,
        CodeEntity,
        CodeFile,
        CodeRelation,
        Project,
        ScanIssue,
    )


def export_code_files(session, project_id: int) -> list[dict[str, Any]]:
    """Export all code_files rows for the project."""
    (
        _,
        _,
        select,
        _,
        _,
        CodeFile,
        _,
        _,
        _,
    ) = _import_backend()

    rows = session.scalars(
        select(CodeFile)
        .where(CodeFile.project_id == project_id)
        .order_by(CodeFile.file_path)
    ).all()
    return [
        {
            "file_path": row.file_path,
            "language": row.language,
            "line_count": row.line_count,
        }
        for row in rows
    ]


def export_code_entities(
    session,
    project_id: int,
    repo_id: str,
    commit_sha: str,
) -> list[dict[str, Any]]:
    """Export all code_entities rows with stable entity keys."""
    (
        _,
        _,
        select,
        _,
        CodeEntity,
        _,
        _,
        _,
        _,
    ) = _import_backend()

    rows = session.scalars(
        select(CodeEntity)
        .where(CodeEntity.project_id == project_id)
        .order_by(CodeEntity.file_path, CodeEntity.start_line, CodeEntity.id)
    ).all()
    results = []
    for row in rows:
        stable_key = _stable_entity_key(
            repo_id=repo_id,
            commit_sha=commit_sha,
            file_path=row.file_path,
            entity_type=row.entity_type,
            qualified_name=row.qualified_name,
            start_line=row.start_line,
            end_line=row.end_line,
        )
        results.append(
            {
                "stable_entity_key": stable_key,
                "entity_type": row.entity_type,
                "name": row.name,
                "qualified_name": row.qualified_name,
                "file_path": row.file_path,
                "start_line": row.start_line,
                "end_line": row.end_line,
                "content_hash": compute_content_hash(row.content),
            }
        )
    return results


def export_code_relations(
    session,
    project_id: int,
    repo_id: str,
    commit_sha: str,
) -> list[dict[str, Any]]:
    """Export all code_relations with stable keys for source and target."""
    (
        _,
        _,
        select,
        _,
        CodeEntity,
        _,
        CodeRelation,
        _,
        _,
    ) = _import_backend()

    # Build a mapping from auto-increment id to entity row so we can
    # compute stable keys for both endpoints.
    entity_rows = session.scalars(
        select(CodeEntity).where(CodeEntity.project_id == project_id)
    ).all()
    id_to_entity = {row.id: row for row in entity_rows}

    relations = session.scalars(
        select(CodeRelation)
        .where(CodeRelation.project_id == project_id)
        .order_by(CodeRelation.id)
    ).all()

    results = []
    for rel in relations:
        source = id_to_entity.get(rel.source_id)
        target = id_to_entity.get(rel.target_id)
        if source is None or target is None:
            continue

        source_key = _stable_entity_key(
            repo_id=repo_id,
            commit_sha=commit_sha,
            file_path=source.file_path,
            entity_type=source.entity_type,
            qualified_name=source.qualified_name,
            start_line=source.start_line,
            end_line=source.end_line,
        )
        target_key = _stable_entity_key(
            repo_id=repo_id,
            commit_sha=commit_sha,
            file_path=target.file_path,
            entity_type=target.entity_type,
            qualified_name=target.qualified_name,
            start_line=target.start_line,
            end_line=target.end_line,
        )
        results.append(
            {
                "relation_type": rel.relation_type,
                "source_key": source_key,
                "target_key": target_key,
                "confidence": rel.confidence,
            }
        )
    return results


def export_scan_issues(
    session,
    project_id: int,
) -> list[dict[str, Any]]:
    """Export all scan_issues rows for the project."""
    (
        _,
        _,
        select,
        _,
        _,
        _,
        _,
        _,
        ScanIssue,
    ) = _import_backend()

    rows = session.scalars(
        select(ScanIssue)
        .where(ScanIssue.project_id == project_id)
        .order_by(ScanIssue.file_path, ScanIssue.id)
    ).all()
    return [
        {
            "file_path": row.file_path,
            "issue_type": row.issue_type,
            "reason_code": row.reason_code,
            "message": row.message,
        }
        for row in rows
    ]


def export_frontend_diagnostics(
    session,
    project_id: int,
) -> dict[str, Any]:
    """Export frontend request matching summary.

    This mirrors the logic in ``IndexService.get_frontend_request_diagnostics``
    but returns a plain dict instead of a Pydantic model.
    """
    (
        _,
        _,
        select,
        func,
        CodeEntity,
        _,
        CodeRelation,
        _,
        ScanIssue,
    ) = _import_backend()

    frontend_entities_q = select(CodeEntity).where(
        CodeEntity.project_id == project_id,
        CodeEntity.entity_type == "frontend_api_call",
    )
    matched_ids_q = (
        select(CodeRelation.source_id)
        .join(CodeEntity, CodeEntity.id == CodeRelation.source_id)
        .where(
            CodeRelation.project_id == project_id,
            CodeRelation.relation_type == "REQUESTS_API",
            CodeEntity.project_id == project_id,
            CodeEntity.entity_type == "frontend_api_call",
        )
        .distinct()
    )

    identified = session.scalar(
        select(func.count()).select_from(frontend_entities_q.subquery())
    ) or 0
    matched = session.scalar(
        select(func.count()).select_from(matched_ids_q.subquery())
    ) or 0

    # Unmatched entities (up to 10 examples).
    from sqlalchemy import not_  # noqa: PLC0415

    unmatched_entities = session.scalars(
        frontend_entities_q.where(CodeEntity.id.not_in(matched_ids_q))
        .order_by(CodeEntity.file_path, CodeEntity.start_line)
        .limit(10)
    ).all()

    unmatched_examples = []
    for entity in unmatched_entities:
        metadata = json.loads(entity.metadata_json)
        unmatched_examples.append(
            {
                "file_path": entity.file_path,
                "start_line": entity.start_line,
                "end_line": entity.end_line,
                "http_method": metadata.get("http_method", ""),
                "path": metadata.get("path", ""),
            }
        )

    # Unresolved candidates (analysis warnings).
    warning_reasons = {
        "FRONTEND_REQUEST_DYNAMIC_URL": "dynamic_url",
        "FRONTEND_REQUEST_DYNAMIC_METHOD": "dynamic_method",
        "FRONTEND_REQUEST_AMBIGUOUS_CONSTANT": "ambiguous_constant",
        "FRONTEND_REQUEST_UNKNOWN_WRAPPER": "unknown_wrapper",
    }
    unresolved_count = session.scalar(
        select(func.count()).select_from(ScanIssue).where(
            ScanIssue.project_id == project_id,
            ScanIssue.issue_type == "analysis_warning",
            ScanIssue.reason_code.in_(warning_reasons),
        )
    ) or 0

    unresolved_issues = session.scalars(
        select(ScanIssue)
        .where(
            ScanIssue.project_id == project_id,
            ScanIssue.issue_type == "analysis_warning",
            ScanIssue.reason_code.in_(warning_reasons),
        )
        .order_by(ScanIssue.file_path, ScanIssue.id)
        .limit(10)
    ).all()

    unresolved_examples = [
        {
            "file_path": issue.file_path,
            "reason": warning_reasons.get(issue.reason_code, issue.reason_code),
            "message": issue.message,
        }
        for issue in unresolved_issues
    ]

    return {
        "identified_calls": identified,
        "matched_calls": matched,
        "unmatched_calls": identified - matched,
        "unresolved_candidates": unresolved_count,
        "unmatched_examples": unmatched_examples,
        "unresolved_examples": unresolved_examples,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_export(
    db_path: Path,
    repo_id: str,
    commit_sha: str,
    output_dir: Path,
) -> None:
    """Read the database and write JSON export files."""
    _configure_backend(db_path)
    (
        create_engine,
        sessionmaker,
        select,
        func,
        CodeEntity,
        CodeFile,
        CodeRelation,
        Project,
        ScanIssue,
    ) = _import_backend()

    db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    # Find the project.  If only one project exists, use it; otherwise
    # use the first project ordered by id.
    project = session.scalars(
        select(Project).order_by(Project.id)
    ).first()
    if project is None:
        print("Error: no projects found in the database.", file=sys.stderr)
        sys.exit(1)
    project_id = project.id

    output_dir.mkdir(parents=True, exist_ok=True)

    # Export each table / view.
    files_data = export_code_files(session, project_id)
    _write_json(output_dir / "code_files.json", files_data)

    entities_data = export_code_entities(session, project_id, repo_id, commit_sha)
    _write_json(output_dir / "code_entities.json", entities_data)

    relations_data = export_code_relations(session, project_id, repo_id, commit_sha)
    _write_json(output_dir / "code_relations.json", relations_data)

    issues_data = export_scan_issues(session, project_id)
    _write_json(output_dir / "scan_issues.json", issues_data)

    diagnostics_data = export_frontend_diagnostics(session, project_id)
    _write_json(output_dir / "frontend_diagnostics.json", diagnostics_data)

    # Write a small manifest for provenance.
    manifest = {
        "repo_id": repo_id,
        "commit_sha": commit_sha,
        "project_id": project_id,
        "project_name": project.name,
        "root_path": project.root_path,
        "file_count": len(files_data),
        "entity_count": len(entities_data),
        "relation_count": len(relations_data),
        "issue_count": len(issues_data),
        "artifacts": {
            "code_files": {
                "path": "code_files.json",
                "sha256": hashlib.sha256((output_dir / "code_files.json").read_bytes()).hexdigest(),
            },
        },
    }
    _write_json(output_dir / "manifest.json", manifest)

    session.close()
    engine.dispose()

    print(
        f"Export complete: {len(files_data)} files, {len(entities_data)} entities, "
        f"{len(relations_data)} relations, {len(issues_data)} issues. "
        f"Output: {output_dir}",
        file=sys.stderr,
    )


def _write_json(path: Path, data: Any) -> None:
    """Write *data* as pretty-printed JSON."""
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export the contents of a ResearchCode-Agent SQLite database "
            "to structured JSON files.  Uses stable entity keys (SHA-256) "
            "for cross-referencing with gold labels."
        ),
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--repo-id",
        required=True,
        type=str,
        help="Repository identifier (used in stable entity key computation).",
    )
    parser.add_argument(
        "--commit-sha",
        required=True,
        type=str,
        help="Full 40-character Git commit SHA (used in stable entity keys).",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory for the exported JSON files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    db_path: Path = args.db
    if not db_path.is_file():
        print(f"Error: database file not found: {db_path}", file=sys.stderr)
        return 1

    commit_sha: str = args.commit_sha
    if len(commit_sha) != 40 or not all(c in "0123456789abcdef" for c in commit_sha):
        print(
            "Error: commit-sha must be a 40-character hex string.",
            file=sys.stderr,
        )
        return 1

    try:
        run_export(db_path, args.repo_id, commit_sha, args.output)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
