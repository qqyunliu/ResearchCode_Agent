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
        if all(
            marker in normalized
            for marker in ("where is", "alert", "implemented")
        ):
            return [1.0, 0.0, 0.0]
        if "alertcontroller" in normalized:
            return [1.0, 0.0, 0.0]
        if "alertservice" in normalized:
            return [0.8, 0.2, 0.0]
        if "alert" in normalized:
            return [0.7, 0.3, 0.0]
        return [0.0, 0.0, 1.0]


class FakeLlm:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return "The alert lookup is implemented in AlertController [1]."


def test_week2_retrieval_and_rag_acceptance(client, tmp_path) -> None:
    embeddings = DeterministicEmbeddings()
    vector_store = QdrantVectorStore(QdrantClient(":memory:"))
    llm = FakeLlm()
    app.dependency_overrides[get_embedding_service] = lambda: embeddings
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_llm_client] = lambda: llm

    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / "week2_acceptance_project"
    shutil.copytree(source, project_root)

    created = client.post(
        "/api/projects",
        json={
            "name": "Week 2 Acceptance",
            "root_path": str(project_root),
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    scanned = client.post(f"/api/projects/{project_id}/scan")
    assert scanned.status_code == 200
    assert scanned.json()["entities_indexed"] == 13

    build = client.post(
        f"/api/projects/{project_id}/build-vector-index"
    )
    assert build.status_code == 200
    assert build.json()["chunks_indexed"] == 13

    keyword = client.post(
        "/api/search/keyword",
        json={
            "project_id": project_id,
            "query": "AlertController",
            "limit": 5,
        },
    )
    assert keyword.status_code == 200
    assert any(
        hit["entity_type"] == "java_class"
        for hit in keyword.json()
    )

    hybrid = client.post(
        "/api/search/hybrid",
        json={
            "project_id": project_id,
            "query": "where is alert lookup implemented",
            "limit": 5,
        },
    )
    assert hybrid.status_code == 200
    assert hybrid.json()[0]["file_path"].endswith(
        "AlertController.java"
    )

    qa = client.post(
        "/api/agent/code-qa",
        json={
            "project_id": project_id,
            "question": "Where is the alert lookup implemented?",
            "limit": 5,
        },
    )
    assert qa.status_code == 200
    assert "[1]" in qa.json()["answer"]
    assert qa.json()["references"]
    assert qa.json()["references"][0]["file_path"].endswith(
        "AlertController.java"
    )
    assert qa.json()["references"][0]["start_line"] >= 1
    assert qa.json()["references"][0]["end_line"] >= (
        qa.json()["references"][0]["start_line"]
    )
    assert len(llm.calls) == 1
    assert "[1]" in llm.calls[0][1]
