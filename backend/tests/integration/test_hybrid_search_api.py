import shutil
from pathlib import Path

from app.core.dependencies import (
    get_embedding_service,
    get_vector_store,
)
from app.main import app
from app.retrieval.hybrid_search import HybridSearchService
from app.retrieval.types import SearchHit


class FakeEmbeddings:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.9, 0.1]


class FakeVectorStore:
    def __init__(
        self,
        hits: list[SearchHit],
        *,
        collection_exists: bool = True,
    ) -> None:
        self.hits = hits
        self.collection_exists = collection_exists
        self.search_calls: list[tuple[int, list[float], int]] = []

    def has_collection(self, project_id: int) -> bool:
        return self.collection_exists

    def search(
        self,
        project_id: int,
        query_vector: list[float],
        limit: int,
    ) -> list[SearchHit]:
        self.search_calls.append((project_id, query_vector, limit))
        return self.hits[:limit]


class FakeKeywordSearch:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[int, str, int]] = []

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        self.calls.append((project_id, query, limit))
        return self.hits[:limit]


def hit(
    entity_id: int,
    score: float,
    source: str,
    *,
    name: str | None = None,
) -> SearchHit:
    entity_name = name or f"method{entity_id}"
    return SearchHit(
        entity_id=entity_id,
        entity_type="java_method",
        name=entity_name,
        qualified_name=f"Demo.{entity_name}",
        file_path="src/Demo.java",
        start_line=1,
        end_line=2,
        content=f"void {entity_name}() {{}}",
        metadata={},
        score=score,
        source=source,
    )


def test_hybrid_service_embeds_once_and_fetches_extra_candidates() -> None:
    embeddings = FakeEmbeddings()
    vector_store = FakeVectorStore([hit(1, 0.8, "vector")])
    keyword_search = FakeKeywordSearch([hit(2, 1.0, "keyword")])
    service = HybridSearchService(
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=keyword_search,
    )

    results = service.search(7, "find alerts", limit=3)

    assert embeddings.queries == ["find alerts"]
    assert vector_store.search_calls == [(7, [0.9, 0.1], 6)]
    assert keyword_search.calls == [(7, "find alerts", 6)]
    assert len(results) == 2
    assert {result.source for result in results} == {"hybrid"}


def create_scanned_project(client, tmp_path) -> int:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / "hybrid_api_project"
    shutil.copytree(source, project_root)
    created = client.post(
        "/api/projects",
        json={
            "name": "Hybrid API Demo",
            "root_path": str(project_root),
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    scanned = client.post(f"/api/projects/{project_id}/scan")
    assert scanned.status_code == 200
    return project_id


def test_hybrid_search_endpoint_merges_duplicate_entity(
    client,
    tmp_path,
) -> None:
    project_id = create_scanned_project(client, tmp_path)
    keyword_response = client.post(
        "/api/search/keyword",
        json={
            "project_id": project_id,
            "query": "getAlert",
            "limit": 1,
        },
    )
    keyword_hit = keyword_response.json()[0]
    vector_hit = SearchHit(
        **{
            **keyword_hit,
            "score": 0.8,
            "source": "vector",
        }
    )
    embeddings = FakeEmbeddings()
    vector_store = FakeVectorStore([vector_hit])
    app.dependency_overrides[get_embedding_service] = lambda: embeddings
    app.dependency_overrides[get_vector_store] = lambda: vector_store

    response = client.post(
        "/api/search/hybrid",
        json={
            "project_id": project_id,
            "query": "getAlert",
            "limit": 2,
        },
    )

    assert response.status_code == 200
    hits = response.json()
    assert [item["entity_id"] for item in hits].count(
        keyword_hit["entity_id"]
    ) == 1
    assert hits[0]["score"] == 1.0
    assert hits[0]["source"] == "hybrid"
    assert embeddings.queries == ["getAlert"]
    assert vector_store.search_calls[0][2] == 4


def test_hybrid_search_requires_vector_index(client, tmp_path) -> None:
    project_id = create_scanned_project(client, tmp_path)
    embeddings = FakeEmbeddings()
    vector_store = FakeVectorStore([], collection_exists=False)
    app.dependency_overrides[get_embedding_service] = lambda: embeddings
    app.dependency_overrides[get_vector_store] = lambda: vector_store

    response = client.post(
        "/api/search/hybrid",
        json={
            "project_id": project_id,
            "query": "alerts",
            "limit": 5,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "VECTOR_INDEX_NOT_FOUND"
    assert embeddings.queries == []
