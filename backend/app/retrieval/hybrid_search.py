from dataclasses import replace
from typing import Protocol

from app.errors import DomainError
from app.retrieval.types import SearchHit
from app.retrieval.query_rewriter import QueryRewriter

VECTOR_FALLBACK_UNCERTAINTY = (
    "Vector retrieval was unavailable; keyword-only fallback was used."
)
KEYWORD_FALLBACK_UNCERTAINTY = (
    "Keyword retrieval was unavailable; vector-only fallback was used."
)
HYBRID_VECTOR_WEIGHT = 0.75
HYBRID_KEYWORD_WEIGHT = 0.25


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class VectorSearcher(Protocol):
    def has_collection(self, project_id: int) -> bool: ...

    def search(
        self,
        project_id: int,
        query_vector: list[float],
        limit: int,
    ) -> list[SearchHit]: ...


class KeywordSearcher(Protocol):
    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]: ...


class HybridSearchService:
    def __init__(
        self,
        *,
        embeddings: QueryEmbedder,
        vector_store: VectorSearcher,
        keyword_search: KeywordSearcher,
        rewriter: QueryRewriter | None = None,
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.keyword_search = keyword_search
        self.rewriter = rewriter

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        vector_unavailable = False
        try:
            has_collection = self.vector_store.has_collection(project_id)
        except Exception:
            has_collection = True
            vector_unavailable = True

        if not has_collection:
            raise DomainError(
                code="VECTOR_INDEX_NOT_FOUND",
                message=(
                    f"Project {project_id} has no vector index. "
                    "Build it before hybrid search."
                ),
                status_code=409,
            )

        candidate_limit = limit * 2
        effective_query = self.rewriter.rewrite(query) if self.rewriter else query
        vector_hits: list[SearchHit] = []
        if not vector_unavailable:
            try:
                query_vector = self.embeddings.embed_query(effective_query)
                vector_hits = self.vector_store.search(
                    project_id,
                    query_vector,
                    candidate_limit,
                )
            except Exception:
                vector_unavailable = True

        keyword_unavailable = False
        try:
            keyword_hits = self.keyword_search.search(
                project_id,
                effective_query,
                candidate_limit,
            )
        except DomainError:
            raise
        except Exception:
            keyword_hits = []
            keyword_unavailable = True

        if vector_unavailable and not keyword_hits:
            raise self._retrieval_unavailable()
        if keyword_unavailable and not vector_hits:
            raise self._retrieval_unavailable()
        if vector_unavailable:
            return [
                replace(
                    hit,
                    source="keyword_fallback",
                    uncertainties=(
                        *hit.uncertainties,
                        VECTOR_FALLBACK_UNCERTAINTY,
                    ),
                )
                for hit in keyword_hits[:limit]
            ]
        if keyword_unavailable:
            return [
                replace(
                    hit,
                    source="vector_fallback",
                    uncertainties=(
                        *hit.uncertainties,
                        KEYWORD_FALLBACK_UNCERTAINTY,
                    ),
                )
                for hit in vector_hits[:limit]
            ]
        return fuse_search_hits(vector_hits, keyword_hits, limit)

    @staticmethod
    def _retrieval_unavailable() -> DomainError:
        return DomainError(
            code="RETRIEVAL_UNAVAILABLE",
            message=(
                "Code retrieval is temporarily unavailable. "
                "Please try again."
            ),
            status_code=503,
        )


def fuse_search_hits(
    vector_hits: list[SearchHit],
    keyword_hits: list[SearchHit],
    limit: int,
) -> list[SearchHit]:
    vector_max = _maximum_positive_score(vector_hits)
    keyword_max = _maximum_positive_score(keyword_hits)
    hits_by_entity: dict[int, SearchHit] = {}
    scores_by_entity: dict[int, float] = {}

    for hit in vector_hits:
        hits_by_entity.setdefault(hit.entity_id, hit)
        scores_by_entity[hit.entity_id] = (
            HYBRID_VECTOR_WEIGHT * _normalize(hit.score, vector_max)
        )

    for hit in keyword_hits:
        hits_by_entity.setdefault(hit.entity_id, hit)
        scores_by_entity[hit.entity_id] = (
            scores_by_entity.get(hit.entity_id, 0.0)
            + HYBRID_KEYWORD_WEIGHT * _normalize(hit.score, keyword_max)
        )

    fused = [
        replace(
            hit,
            score=scores_by_entity[entity_id],
            source="hybrid",
        )
        for entity_id, hit in hits_by_entity.items()
    ]
    fused.sort(key=lambda hit: (-hit.score, hit.entity_id))
    return fused[:limit]


def _maximum_positive_score(hits: list[SearchHit]) -> float:
    return max(
        (hit.score for hit in hits if hit.score > 0),
        default=0.0,
    )


def _normalize(score: float, maximum: float) -> float:
    if score <= 0 or maximum <= 0:
        return 0.0
    return score / maximum
