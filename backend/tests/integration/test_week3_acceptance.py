import shutil
from pathlib import Path

from qdrant_client import QdrantClient

from app.core.dependencies import (
    get_embedding_service,
    get_llm_client,
    get_vector_store,
)
from app.main import app
from app.retrieval.vector_store import QdrantVectorStore


class DeterministicEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if "alertcontroller" in normalized or "get /api/alerts" in normalized:
            return [1.0, 0.0, 0.0]
        if "alertservice" in normalized or "findbyid" in normalized:
            return [0.8, 0.2, 0.0]
        if "alert" in normalized:
            return [0.7, 0.3, 0.0]
        return [0.0, 0.0, 1.0]


class FakeLlm:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return (
            "The frontend requests the API, which calls the controller "
            "and service [1]."
        )


def create_project(client, tmp_path, name: str) -> int:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / name
    shutil.copytree(source, project_root)
    response = client.post(
        "/api/projects",
        json={"name": name, "root_path": str(project_root)},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    scan = client.post(f"/api/projects/{project_id}/scan")
    assert scan.status_code == 200
    assert scan.json()["relations_indexed"] == 10
    return project_id


def test_week3_graph_and_trace_acceptance(client, tmp_path) -> None:
    embeddings = DeterministicEmbeddings()
    vector_store = QdrantVectorStore(QdrantClient(":memory:"))
    llm = FakeLlm()
    app.dependency_overrides[get_embedding_service] = lambda: embeddings
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_llm_client] = lambda: llm

    project_id = create_project(client, tmp_path, "week3-primary")
    other_project_id = create_project(client, tmp_path, "week3-other")

    stats = client.get(f"/api/projects/{project_id}/stats")
    assert stats.status_code == 200
    assert stats.json()["relation_types"] == {
        "CALLS_METHOD": 1,
        "CONTAINS": 5,
        "DEFINES_API": 2,
        "REQUESTS_API": 2,
    }

    exact = client.get(
        "/api/graph/api-chain",
        params={
            "project_id": project_id,
            "method": "GET",
            "api_path": "/api/alerts/123",
        },
    )
    assert exact.status_code == 200
    assert {
        edge["relation_type"] for edge in exact.json()["edges"]
    } == {
        "REQUESTS_API",
        "DEFINES_API",
        "CALLS_METHOD",
    }

    build = client.post(
        f"/api/projects/{project_id}/build-vector-index"
    )
    assert build.status_code == 200
    assert build.json()["chunks_indexed"] == 13

    search_chain = client.post(
        "/api/graph/search-chain",
        json={
            "project_id": project_id,
            "query": "Where is the alert API implemented?",
            "limit": 5,
            "max_depth": 2,
        },
    )
    assert search_chain.status_code == 200
    search_data = search_chain.json()
    assert search_data["nodes"]
    assert "CALLS_METHOD" in {
        edge["relation_type"] for edge in search_data["edges"]
    }

    trace = client.post(
        "/api/agent/trace",
        json={
            "project_id": project_id,
            "question": "Trace the alert GET request.",
            "limit": 5,
            "max_depth": 2,
        },
    )
    assert trace.status_code == 200
    trace_data = trace.json()
    assert "[1]" in trace_data["answer"]
    assert trace_data["references"]
    assert trace_data["uncertainties"] == []
    graph_node_ids = {
        node["entity_id"] for node in trace_data["graph_nodes"]
    }
    assert all(
        edge["source_id"] in graph_node_ids
        and edge["target_id"] in graph_node_ids
        for edge in trace_data["graph_edges"]
    )
    assert all(
        reference["entity_id"] in graph_node_ids
        for reference in trace_data["references"]
    )

    other_keyword = client.post(
        "/api/search/keyword",
        json={
            "project_id": other_project_id,
            "query": "AlertController",
            "limit": 20,
        },
    )
    other_entity_ids = {
        hit["entity_id"] for hit in other_keyword.json()
    }
    assert graph_node_ids.isdisjoint(other_entity_ids)
    assert len(llm.calls) == 1
    assert "Stored graph edges (authoritative):" in llm.calls[0][1]
