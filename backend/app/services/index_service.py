import json
import threading
from dataclasses import replace
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import (
    CodeEntity,
    CodeFile,
    CodeRelation,
    Project,
    ScanIssue,
)
from app.models.base import utc_now
from app.parsers.base import (
    EntityCandidate,
    ParseResult,
    RelationCandidate,
    entity_key,
)
from app.parsers.registry import ParserRegistry
from app.parsers.relation_builder import build_relations
from app.schemas.scan import ScanSummary
from app.services.scanner import (
    ProjectScanner,
    ScanIssueCandidate,
    ScannedFile,
)


class IndexService:
    _project_locks: dict[int, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(
        self,
        session: Session,
        *,
        scanner: ProjectScanner | None = None,
        registry: ParserRegistry | None = None,
    ) -> None:
        self.session = session
        self.scanner = scanner or ProjectScanner()
        self.registry = registry or ParserRegistry()

    def scan_project(self, project_id: int) -> ScanSummary:
        project = self.session.get(Project, project_id)
        if project is None:
            raise DomainError(
                code="PROJECT_NOT_FOUND",
                message=f"Project {project_id} does not exist.",
                status_code=404,
            )
        root_path = Path(project.root_path)
        self.session.rollback()

        lock = self._project_lock(project_id)
        if not lock.acquire(blocking=False):
            raise DomainError(
                code="SCAN_ALREADY_RUNNING",
                message=f"Project {project_id} is already being scanned.",
                status_code=409,
            )

        try:
            scan_result = self.scanner.scan(root_path)
            entities, parser_relations, parse_issues = self._parse_files(
                scan_result.files
            )
            relations = build_relations(entities, parser_relations)
            issues = [*scan_result.issues, *parse_issues]
            self._replace_index(
                project_id,
                scan_result.files,
                entities,
                relations,
                issues,
            )
            return ScanSummary(
                project_id=project_id,
                status="ready",
                files_indexed=len(scan_result.files),
                entities_indexed=len(entities),
                relations_indexed=len(relations),
                files_skipped=sum(
                    issue.issue_type == "skipped" for issue in issues
                ),
                parse_errors=sum(
                    issue.issue_type == "parse_error" for issue in issues
                ),
            )
        except Exception:
            self.session.rollback()
            self._mark_failed(project_id)
            raise
        finally:
            lock.release()

    def _parse_files(
        self,
        files: tuple[ScannedFile, ...],
    ) -> tuple[
        list[EntityCandidate],
        list[RelationCandidate],
        list[ScanIssueCandidate],
    ]:
        entities: list[EntityCandidate] = []
        relations: list[RelationCandidate] = []
        issues: list[ScanIssueCandidate] = []

        for scanned_file in files:
            try:
                result = self.registry.parse(scanned_file)
            except Exception as error:
                issues.append(
                    ScanIssueCandidate(
                        file_path=scanned_file.file_path,
                        issue_type="parse_error",
                        reason_code="PARSER_ERROR",
                        message=str(error),
                    )
                )
                continue
            namespaced = self._namespace_result(scanned_file.file_path, result)
            entities.extend(namespaced.entities)
            relations.extend(namespaced.relations)

        return entities, relations, issues

    def _replace_index(
        self,
        project_id: int,
        files: tuple[ScannedFile, ...],
        entities: list[EntityCandidate],
        relations: tuple[RelationCandidate, ...],
        issues: list[ScanIssueCandidate],
    ) -> None:
        project = self.session.get(Project, project_id)
        if project is None:
            raise RuntimeError(f"Project {project_id} disappeared during scan.")
        project.status = "scanning"

        self.session.execute(
            delete(CodeRelation).where(CodeRelation.project_id == project_id)
        )
        self.session.execute(
            delete(CodeEntity).where(CodeEntity.project_id == project_id)
        )
        self.session.execute(
            delete(CodeFile).where(CodeFile.project_id == project_id)
        )
        self.session.execute(
            delete(ScanIssue).where(ScanIssue.project_id == project_id)
        )

        file_rows = {
            scanned_file.file_path: CodeFile(
                project_id=project_id,
                file_path=scanned_file.file_path,
                language=scanned_file.language,
                line_count=scanned_file.line_count,
                file_hash=scanned_file.file_hash,
                size_bytes=scanned_file.size_bytes,
            )
            for scanned_file in files
        }
        self.session.add_all(file_rows.values())
        self.session.flush()

        entity_rows = {
            candidate.local_key: CodeEntity(
                project_id=project_id,
                file_id=file_rows[candidate.file_path].id,
                entity_key=entity_key(candidate),
                entity_type=candidate.entity_type,
                name=candidate.name,
                qualified_name=candidate.qualified_name,
                file_path=candidate.file_path,
                start_line=candidate.start_line,
                end_line=candidate.end_line,
                content=candidate.content,
                metadata_json=json.dumps(
                    candidate.metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            for candidate in entities
        }
        self.session.add_all(entity_rows.values())
        self.session.flush()

        for relation in relations:
            source = entity_rows.get(relation.source_key)
            target = entity_rows.get(relation.target_key)
            if source is None or target is None:
                continue
            self.session.add(
                CodeRelation(
                    project_id=project_id,
                    source_id=source.id,
                    target_id=target.id,
                    relation_type=relation.relation_type,
                    confidence=relation.confidence,
                    metadata_json=json.dumps(
                        relation.metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )

        self.session.add_all(
            ScanIssue(
                project_id=project_id,
                file_path=issue.file_path,
                issue_type=issue.issue_type,
                reason_code=issue.reason_code,
                message=issue.message,
            )
            for issue in issues
        )
        project.status = "ready"
        project.last_scan_at = utc_now()
        self.session.commit()

    def _mark_failed(self, project_id: int) -> None:
        try:
            project = self.session.get(Project, project_id)
            if project is not None:
                project.status = "failed"
                self.session.commit()
        except Exception:
            self.session.rollback()

    @classmethod
    def _project_lock(cls, project_id: int) -> threading.Lock:
        with cls._locks_guard:
            return cls._project_locks.setdefault(
                project_id,
                threading.Lock(),
            )

    @staticmethod
    def _namespace_result(file_path: str, result: ParseResult) -> ParseResult:
        prefix = f"{file_path}::"
        return ParseResult(
            entities=tuple(
                replace(entity, local_key=f"{prefix}{entity.local_key}")
                for entity in result.entities
            ),
            relations=tuple(
                replace(
                    relation,
                    source_key=f"{prefix}{relation.source_key}",
                    target_key=f"{prefix}{relation.target_key}",
                )
                for relation in result.relations
            ),
        )
