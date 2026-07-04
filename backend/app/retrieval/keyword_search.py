import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import CodeEntity, Project
from app.retrieval.types import SearchHit


class KeywordSearchService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        if self.session.get(Project, project_id) is None:
            raise DomainError(
                code="PROJECT_NOT_FOUND",
                message=f"Project {project_id} does not exist.",
                status_code=404,
            )

        normalized_query = query.casefold()
        pattern = f"%{self._escape_like(normalized_query)}%"
        searchable_columns = (
            CodeEntity.name,
            CodeEntity.qualified_name,
            CodeEntity.metadata_json,
            CodeEntity.file_path,
            CodeEntity.content,
        )
        entities = self.session.scalars(
            select(CodeEntity)
            .where(
                CodeEntity.project_id == project_id,
                or_(
                    *[
                        func.lower(column).like(pattern, escape="\\")
                        for column in searchable_columns
                    ]
                ),
            )
            .order_by(CodeEntity.id)
        ).all()

        ranked = [
            (self._score(entity, normalized_query), entity)
            for entity in entities
        ]
        ranked = [
            (score, entity)
            for score, entity in ranked
            if score > 0
        ]
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return [
            self._to_hit(entity, score)
            for score, entity in ranked[:limit]
        ]

    @staticmethod
    def _escape_like(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    @staticmethod
    def _score(entity: CodeEntity, query: str) -> float:
        name = entity.name.casefold()
        qualified_name = entity.qualified_name.casefold()
        metadata = entity.metadata_json.casefold()
        file_path = entity.file_path.casefold()
        content = entity.content.casefold()

        scores: list[float] = []
        if name == query:
            scores.append(1.0)
        if query in qualified_name:
            scores.append(0.9)
        if query.startswith("/") and (
            query in metadata or query in name
        ):
            scores.append(0.85)
        if query in name:
            scores.append(0.75)
        if query in file_path:
            scores.append(0.6)
        if query in content:
            scores.append(0.4)
        return max(scores, default=0.0)

    @staticmethod
    def _to_hit(entity: CodeEntity, score: float) -> SearchHit:
        metadata = json.loads(entity.metadata_json)
        if not isinstance(metadata, dict):
            raise ValueError("entity metadata_json must contain an object")
        return SearchHit(
            entity_id=entity.id,
            entity_type=entity.entity_type,
            name=entity.name,
            qualified_name=entity.qualified_name,
            file_path=entity.file_path,
            start_line=entity.start_line,
            end_line=entity.end_line,
            content=entity.content,
            metadata=metadata,
            score=score,
            source="keyword",
        )
