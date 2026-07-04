from dataclasses import replace
from typing import Protocol

from app.errors import DomainError
from app.retrieval.types import SearchHit


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
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.keyword_search = keyword_search

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        if not self.vector_store.has_collection(project_id):
            raise DomainError(
                code="VECTOR_INDEX_NOT_FOUND",
                message=(
                    f"Project {project_id} has no vector index. "
                    "Build it before hybrid search."
                ),
                status_code=409,
            )

        candidate_limit = limit * 2
        query_vector = self.embeddings.embed_query(query)
        vector_hits = self.vector_store.search(
            project_id,
            query_vector,
            candidate_limit,
        )
        keyword_hits = self.keyword_search.search(
            project_id,
            query,
            candidate_limit,
        )
        return fuse_search_hits(vector_hits, keyword_hits, limit)


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
            0.7 * _normalize(hit.score, vector_max)
        )

    for hit in keyword_hits:
        hits_by_entity.setdefault(hit.entity_id, hit)
        scores_by_entity[hit.entity_id] = (
            scores_by_entity.get(hit.entity_id, 0.0)
            + 0.3 * _normalize(hit.score, keyword_max)
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
