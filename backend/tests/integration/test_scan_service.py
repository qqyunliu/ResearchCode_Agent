import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.errors import DomainError
from app.models import (
    Base,
    CodeEntity,
    CodeFile,
    CodeRelation,
    Project,
    ScanIssue,
)
from app.parsers.registry import ParserRegistry
from app.services.index_service import IndexService


@pytest.fixture
def scan_context(tmp_path):
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / "sample_project"
    shutil.copytree(source, project_root)

    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'scan.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with session_factory() as session:
        project = Project(name="Sample", root_path=str(project_root))
        session.add(project)
        session.commit()
        session.refresh(project)
        yield session, project, project_root

    engine.dispose()


def count(session: Session, model: type, project_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(model).where(
            model.project_id == project_id
        )
    )


def test_scan_persists_counts_and_rescan_replaces_without_duplicates(
    scan_context,
) -> None:
    session, project, _ = scan_context
    service = IndexService(session)

    first = service.scan_project(project.id)
    second = service.scan_project(project.id)

    assert second.files_indexed == first.files_indexed == count(
        session, CodeFile, project.id
    )
    assert second.entities_indexed == first.entities_indexed == count(
        session, CodeEntity, project.id
    )
    assert second.relations_indexed == first.relations_indexed == count(
        session, CodeRelation, project.id
    )
    assert second.status == "ready"
    duplicate_entity_keys = session.execute(
        select(CodeEntity.entity_key, func.count())
        .where(CodeEntity.project_id == project.id)
        .group_by(CodeEntity.entity_key)
        .having(func.count() > 1)
    ).all()
    duplicate_edges = session.execute(
        select(
            CodeRelation.source_id,
            CodeRelation.target_id,
            CodeRelation.relation_type,
            func.count(),
        )
        .where(CodeRelation.project_id == project.id)
        .group_by(
            CodeRelation.source_id,
            CodeRelation.target_id,
            CodeRelation.relation_type,
        )
        .having(func.count() > 1)
    ).all()

    assert duplicate_entity_keys == []
    assert duplicate_edges == []
    session.refresh(project)
    assert project.status == "ready"
    assert project.last_scan_at is not None


def test_rescan_removes_deleted_file_and_its_entities(scan_context) -> None:
    session, project, project_root = scan_context
    service = IndexService(session)
    first = service.scan_project(project.id)
    (project_root / "algorithm" / "detector.py").unlink()

    second = service.scan_project(project.id)

    assert second.files_indexed == first.files_indexed - 1
    assert session.scalar(
        select(CodeFile).where(
            CodeFile.project_id == project.id,
            CodeFile.file_path == "algorithm/detector.py",
        )
    ) is None
    assert session.scalars(
        select(CodeEntity).where(
            CodeEntity.project_id == project.id,
            CodeEntity.file_path == "algorithm/detector.py",
        )
    ).all() == []


class FailingRegistry:
    def __init__(self) -> None:
        self.registry = ParserRegistry()

    def parse(self, scanned_file):
        if scanned_file.file_path.endswith("AlertController.java"):
            raise RuntimeError("intentional parser failure")
        return self.registry.parse(scanned_file)


def test_parser_failure_is_recorded_while_other_files_are_indexed(
    scan_context,
) -> None:
    session, project, _ = scan_context

    summary = IndexService(
        session,
        registry=FailingRegistry(),
    ).scan_project(project.id)

    issue = session.scalar(
        select(ScanIssue).where(ScanIssue.project_id == project.id)
    )
    assert summary.parse_errors == 1
    assert summary.files_indexed == 5
    assert issue is not None
    assert issue.issue_type == "parse_error"
    assert issue.file_path == "backend/src/AlertController.java"
    assert count(session, CodeEntity, project.id) > 0


def test_missing_project_raises_domain_error(scan_context) -> None:
    session, _, _ = scan_context

    with pytest.raises(DomainError) as error:
        IndexService(session).scan_project(999)

    assert error.value.code == "PROJECT_NOT_FOUND"
    assert error.value.status_code == 404


def test_concurrent_scan_for_same_project_is_rejected(scan_context) -> None:
    session, project, _ = scan_context
    lock = IndexService._project_lock(project.id)
    lock.acquire()
    try:
        with pytest.raises(DomainError) as error:
            IndexService(session).scan_project(project.id)
    finally:
        lock.release()

    assert error.value.code == "SCAN_ALREADY_RUNNING"
    assert error.value.status_code == 409


class InvalidMetadataRegistry:
    def __init__(self) -> None:
        self.registry = ParserRegistry()
        self.corrupted = False

    def parse(self, scanned_file):
        result = self.registry.parse(scanned_file)
        if self.corrupted or not result.entities:
            return result
        self.corrupted = True
        first, *remaining = result.entities
        return replace(
            result,
            entities=(
                replace(first, metadata={"not_json": {"a", "set"}}),
                *remaining,
            ),
        )


def test_failed_replacement_preserves_previous_index(scan_context) -> None:
    session, project, _ = scan_context
    service = IndexService(session)
    successful = service.scan_project(project.id)

    with pytest.raises(TypeError):
        IndexService(
            session,
            registry=InvalidMetadataRegistry(),
        ).scan_project(project.id)

    assert count(session, CodeFile, project.id) == successful.files_indexed
    assert count(session, CodeEntity, project.id) == successful.entities_indexed
    assert count(session, CodeRelation, project.id) == successful.relations_indexed
    session.refresh(project)
    assert project.status == "failed"
