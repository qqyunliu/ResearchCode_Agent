#!/usr/bin/env python3
"""Scan a repository using ResearchCode-Agent's scanning infrastructure.

Creates an isolated SQLite database, registers the target project, runs
the full static-analysis scan (Java/Vue/Python parsers + frontend-request
resolution + relation extraction), and prints detailed statistics.

Usage:
    python scan_pilot_repo.py --repo REPO_PATH --db DB_PATH [--name NAME]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: make the backend package importable.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPTS_DIR.parent.parent / "backend"

# Insert backend at the front of sys.path so ``import app.xxx`` resolves.
_BACKEND_DIR_STR = str(_BACKEND_DIR)
if _BACKEND_DIR_STR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR_STR)


def _configure_environment(db_path: Path) -> None:
    """Set environment variables BEFORE any backend import.

    The backend's ``app.core.database`` module creates the SQLAlchemy engine
    at import time from ``get_settings().database_url``.  We must therefore
    set ``RCA_DATABASE_URL`` before that import happens.
    """
    db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    os.environ["RCA_DATABASE_URL"] = db_url

    # Disable Qdrant / LLM / embedding env vars that the scanner doesn't
    # need but that might cause validation errors if missing.
    # (These are only needed for vector indexing and chat, not scanning.)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan a repository with ResearchCode-Agent's static analysis pipeline.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        help="Path to the repository root to scan.",
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="Path for the isolated SQLite database to create.",
    )
    parser.add_argument(
        "--name",
        default="RuoYi-Vue",
        help="Project name to register (default: RuoYi-Vue).",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    repo_path: Path = args.repo.resolve()
    db_path: Path = args.db

    if not repo_path.is_dir():
        print(f"Error: repository path is not a directory: {repo_path}", file=sys.stderr)
        return 1

    # Ensure the parent directory for the DB exists.
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove an existing DB to start fresh.
    if db_path.exists():
        db_path.unlink()
        print(f"Removed existing database: {db_path}")

    # ---- Configure environment before importing backend ----
    _configure_environment(db_path)

    # ---- Now import backend modules ----
    # These imports happen AFTER RCA_DATABASE_URL is set.
    #
    # IMPORTANT: ``app.agent.types`` must be imported before
    # ``app.services`` to break a circular import chain:
    #   services.__init__ -> trace_service -> schemas.agent
    #   -> agent.__init__ -> agent.executor -> schemas.agent (CIRCULAR)
    # Importing agent.types first bootstraps the chain cleanly because
    # it uses TYPE_CHECKING guards for cross-package references.

    import app.agent.types  # noqa: F401, E402  (circular-import breaker)

    from sqlalchemy import func, select  # noqa: E402
    from app.core.database import SessionLocal, engine  # noqa: E402
    from app.models import (  # noqa: E402
        Base,
        CodeEntity,
        CodeFile,
        CodeRelation,
        Project,
        ScanIssue,
    )
    from app.services.index_service import IndexService  # noqa: E402
    from app.services.project_service import ProjectService  # noqa: E402
    from app.schemas.project import ProjectCreate  # noqa: E402

    # ---- Create database tables ----
    print("Creating database tables...")
    Base.metadata.create_all(engine)

    # ---- Register the project ----
    print(f"Registering project: name={args.name!r}, root={repo_path}")
    with SessionLocal() as session:
        # Check if a project with this root_path already exists.
        root_path_str = str(repo_path)
        existing = session.scalar(
            select(Project).where(Project.root_path == root_path_str)
        )
        if existing is not None:
            project = existing
            print(f"Using existing project: id={project.id}")
        else:
            project = ProjectService(session).create(
                ProjectCreate(name=args.name, root_path=root_path_str)
            )
            print(f"Created project: id={project.id}")

        # ---- Run the scan ----
        print(f"\nStarting scan of {repo_path} ...")
        scan_start = time.monotonic()

        index_service = IndexService(session)
        summary = index_service.scan_project(project.id)

        scan_end = time.monotonic()
        scan_duration = scan_end - scan_start

        # ---- Print scan summary ----
        print(f"\n{'=' * 60}")
        print("SCAN COMPLETE")
        print(f"{'=' * 60}")
        print(f"  Status:           {summary.status}")
        print(f"  Files indexed:    {summary.files_indexed}")
        print(f"  Entities indexed: {summary.entities_indexed}")
        print(f"  Relations indexed:{summary.relations_indexed}")
        print(f"  Files skipped:    {summary.files_skipped}")
        print(f"  Parse errors:     {summary.parse_errors}")
        print(f"  Scan duration:    {scan_duration:.2f}s")

        # ---- Detailed statistics ----
        print(f"\n{'=' * 60}")
        print("DETAILED STATISTICS")
        print(f"{'=' * 60}")

        # Files by language
        print("\n--- Files by language ---")
        lang_rows = session.execute(
            select(CodeFile.language, func.count(), func.sum(CodeFile.line_count))
            .where(CodeFile.project_id == project.id)
            .group_by(CodeFile.language)
            .order_by(func.count().desc())
        ).all()
        total_files = 0
        total_lines = 0
        for lang, count, lines in lang_rows:
            print(f"  {lang:15s}: {count:5d} files, {lines or 0:8d} lines")
            total_files += count
            total_lines += lines or 0
        print(f"  {'TOTAL':15s}: {total_files:5d} files, {total_lines:8d} lines")

        # Entities by type
        print("\n--- Entities by type ---")
        entity_rows = session.execute(
            select(CodeEntity.entity_type, func.count())
            .where(CodeEntity.project_id == project.id)
            .group_by(CodeEntity.entity_type)
            .order_by(func.count().desc())
        ).all()
        total_entities = 0
        for etype, count in entity_rows:
            print(f"  {etype:25s}: {count:5d}")
            total_entities += count
        print(f"  {'TOTAL':25s}: {total_entities:5d}")

        # Relations by type
        print("\n--- Relations by type ---")
        rel_rows = session.execute(
            select(CodeRelation.relation_type, func.count())
            .where(CodeRelation.project_id == project.id)
            .group_by(CodeRelation.relation_type)
            .order_by(func.count().desc())
        ).all()
        total_relations = 0
        for rtype, count in rel_rows:
            print(f"  {rtype:25s}: {count:5d}")
            total_relations += count
        print(f"  {'TOTAL':25s}: {total_relations:5d}")

        # Scan issues by type and reason
        print("\n--- Scan issues ---")
        issue_rows = session.execute(
            select(ScanIssue.issue_type, ScanIssue.reason_code, func.count())
            .where(ScanIssue.project_id == project.id)
            .group_by(ScanIssue.issue_type, ScanIssue.reason_code)
            .order_by(func.count().desc())
        ).all()
        total_issues = 0
        for itype, reason, count in issue_rows:
            print(f"  {itype:20s} / {reason:40s}: {count:5d}")
            total_issues += count
        print(f"  {'TOTAL issues':63s}: {total_issues:5d}")

        # Frontend request diagnostics
        print("\n--- Frontend request diagnostics ---")
        frontend_count = session.scalar(
            select(func.count()).select_from(CodeEntity).where(
                CodeEntity.project_id == project.id,
                CodeEntity.entity_type == "frontend_api_call",
            )
        ) or 0
        matched_count = session.scalar(
            select(func.count())
            .select_from(CodeRelation)
            .join(CodeEntity, CodeEntity.id == CodeRelation.source_id)
            .where(
                CodeRelation.project_id == project.id,
                CodeRelation.relation_type == "REQUESTS_API",
                CodeEntity.project_id == project.id,
                CodeEntity.entity_type == "frontend_api_call",
            )
        ) or 0
        print(f"  Frontend API call entities: {frontend_count}")
        print(f"  Matched via REQUESTS_API:  {matched_count}")
        print(f"  Unmatched:                 {frontend_count - matched_count}")

        # Backend API count
        backend_api_count = session.scalar(
            select(func.count()).select_from(CodeEntity).where(
                CodeEntity.project_id == project.id,
                CodeEntity.entity_type == "backend_api",
            )
        ) or 0
        print(f"  Backend API entities:      {backend_api_count}")

        print(f"\n{'=' * 60}")
        print(f"Database: {db_path}")
        print(f"Project ID: {project.id}")
        print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
