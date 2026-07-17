import json
from functools import lru_cache
import unicodedata

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import CodeEntity, Project
from app.retrieval.lexical_query import parse_lexical_terms
from app.retrieval.types import SearchHit


LEXICAL_IMPLEMENTATION_VERSION = "code_aware_multiterm_v2"

_LEXICAL_SCORE_UDF = "rca_lexical_score"
_LEXICAL_SCORE_UDF_INFO_KEY = "rca_lexical_score_registered_v2"
_LOW_INFORMATION_TERMS = frozenset(
    {
        "api",
        "class",
        "code",
        "controller",
        "endpoint",
        "file",
        "http",
        "method",
        "module",
        "path",
    }
)


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).casefold()


def _legacy_field_score(
    normalized_fields: tuple[str, str, str, str, str],
    term: str,
) -> float:
    name, qualified_name, metadata, file_path, content = normalized_fields
    scores: list[float] = []
    if name == term:
        scores.append(1.0)
    if term in qualified_name:
        scores.append(0.9)
    if term.startswith("/") and (term in metadata or term in name):
        scores.append(0.85)
    if term in name:
        scores.append(0.75)
    if term in file_path:
        scores.append(0.6)
    if term in content:
        scores.append(0.4)
    return max(scores, default=0.0)


def _score_lexical_fields(
    terms: tuple[str, ...],
    name: object,
    qualified_name: object,
    metadata: object,
    file_path: object,
    content: object,
) -> float:
    """Score already-parsed terms against five entity fields without I/O."""

    normalized_terms = tuple(_normalize_text(term) for term in terms)
    normalized_fields = tuple(
        _normalize_text(value)
        for value in (name, qualified_name, metadata, file_path, content)
    )
    if len(normalized_terms) == 1:
        return _legacy_field_score(normalized_fields, normalized_terms[0])

    weights = tuple(
        0.25 if term in _LOW_INFORMATION_TERMS else 1.0
        for term in normalized_terms
    )
    term_scores = tuple(
        _legacy_field_score(normalized_fields, term)
        for term in normalized_terms
    )
    total_weight = sum(weights)
    matched_weight = sum(
        weight
        for weight, score in zip(weights, term_scores, strict=True)
        if score > 0
    )
    weighted_score_sum = sum(
        weight * score
        for weight, score in zip(weights, term_scores, strict=True)
    )
    return (
        0.6 * matched_weight / total_weight
        + 0.4 * weighted_score_sum / total_weight
    )


@lru_cache(maxsize=128)
def _decode_terms(payload: str) -> tuple[str, ...]:
    decoded = json.loads(payload)
    if not isinstance(decoded, list) or not all(
        isinstance(term, str) for term in decoded
    ):
        raise ValueError("lexical score payload must be a list of strings")
    return tuple(decoded)


def _sqlite_lexical_score(
    payload: str,
    name: object,
    qualified_name: object,
    metadata: object,
    file_path: object,
    content: object,
) -> float:
    return _score_lexical_fields(
        _decode_terms(payload),
        name,
        qualified_name,
        metadata,
        file_path,
        content,
    )


class KeywordSearchService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        if self.session.get(Project, project_id) is None:
            raise DomainError(
                code="PROJECT_NOT_FOUND",
                message=f"Project {project_id} does not exist.",
                status_code=404,
            )

        terms = parse_lexical_terms(query)
        if not terms:
            literal_query = _normalize_text(query.strip())
            if literal_query == "\\":
                terms = (literal_query,)
            else:
                return []

        self._ensure_lexical_score_udf()
        normalized_query = _normalize_text(query.strip())
        is_structured_query = (
            len(terms) > 1 and terms[0] == normalized_query
        )
        if is_structured_query:
            scored_entities, score_expression = self._structured_scored_cte(
                project_id,
                complete_term=terms[0],
                component_terms=terms[1:],
            )
        else:
            scored_entities, score_expression = self._plain_scored_cte(
                project_id,
                terms,
            )

        labeled_score = score_expression.label("lexical_score")
        rows = self.session.execute(
            select(CodeEntity, labeled_score)
            .join(
                scored_entities,
                scored_entities.c.entity_id == CodeEntity.id,
            )
            .where(
                score_expression > 0,
            )
            .order_by(labeled_score.desc(), CodeEntity.id.asc())
            .limit(limit)
        ).all()
        return [
            self._to_hit(entity, float(score))
            for entity, score in rows
        ]

    def _ensure_lexical_score_udf(self) -> None:
        connection = self.session.connection()
        if connection.dialect.name != "sqlite":
            raise RuntimeError("keyword lexical scoring requires SQLite")
        if connection.info.get(_LEXICAL_SCORE_UDF_INFO_KEY):
            return

        driver_connection = connection.connection.driver_connection
        driver_connection.create_function(
            _LEXICAL_SCORE_UDF,
            6,
            _sqlite_lexical_score,
            deterministic=True,
        )
        connection.info[_LEXICAL_SCORE_UDF_INFO_KEY] = True

    @staticmethod
    def _score_expression(terms: tuple[str, ...], entity) -> object:
        payload = json.dumps(terms, ensure_ascii=False, separators=(",", ":"))
        return getattr(func, _LEXICAL_SCORE_UDF)(
            payload,
            entity.name,
            entity.qualified_name,
            entity.metadata_json,
            entity.file_path,
            entity.content,
        )

    def _plain_scored_cte(
        self,
        project_id: int,
        terms: tuple[str, ...],
    ):
        score = self._score_expression(terms, CodeEntity)
        scored_entities = (
            select(
                CodeEntity.id.label("entity_id"),
                score.label("lexical_score"),
            )
            .where(CodeEntity.project_id == project_id)
            .cte("project_lexical_scores")
            .prefix_with("MATERIALIZED")
        )
        return scored_entities, scored_entities.c.lexical_score

    def _structured_scored_cte(
        self,
        project_id: int,
        *,
        complete_term: str,
        component_terms: tuple[str, ...],
    ):
        complete_score = self._score_expression((complete_term,), CodeEntity)
        component_score = self._score_expression(
            component_terms,
            CodeEntity,
        )
        scored_entities = (
            select(
                CodeEntity.id.label("entity_id"),
                complete_score.label("complete_score"),
                component_score.label("component_score"),
            )
            .where(CodeEntity.project_id == project_id)
            .cte("project_structured_lexical_scores")
            .prefix_with("MATERIALIZED")
        )
        complete_match_exists = (
            select(1)
            .select_from(scored_entities)
            .where(
                scored_entities.c.complete_score > 0,
            )
            .exists()
        )
        effective_score = case(
            (complete_match_exists, scored_entities.c.complete_score),
            else_=scored_entities.c.component_score,
        )
        return scored_entities, effective_score

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
