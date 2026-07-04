import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.dependencies import (
    get_chunk_builder,
    get_embedding_service,
    get_vector_store,
)
from app.main import app
from app.retrieval.chunk_builder import CodeChunkBuilder
from app.retrieval.types import CodeChunk


class FakeEmbeddings:
    def __init__(self) -> None:
        self.document_texts: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_texts = texts
        return [
            [float(index), 1.0]
            for index, _ in enumerate(texts, start=1)
        ]


class FakeVectorStore:
    def __init__(self) -> None:
        self.project_id: int | None = None
        self.chunks: list[CodeChunk] = []
        self.vectors: list[list[float]] = []

    @staticmethod
    def collection_name(project_id: int) -> str:
        return f"project_{project_id}_code_chunks"

    def rebuild(
        self,
        project_id: int,
        chunks: list[CodeChunk],
        vectors: list[list[float]],
    ) -> None:
        self.project_id = project_id
        self.chunks = list(chunks)
        self.vectors = list(vectors)


@pytest.fixture(autouse=True)
def fake_retrieval_dependencies(
) -> Iterator[tuple[FakeEmbeddings, FakeVectorStore]]:
    fake_embeddings = FakeEmbeddings()
    fake_store = FakeVectorStore()
    app.dependency_overrides[get_chunk_builder] = CodeChunkBuilder
    app.dependency_overrides[get_embedding_service] = (
        lambda: fake_embeddings
    )
    app.dependency_overrides[get_vector_store] = lambda: fake_store
    yield fake_embeddings, fake_store


def create_project(client, tmp_path, *, scan: bool) -> int:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / ("scanned" if scan else "unscanned")
    shutil.copytree(source, project_root)
    response = client.post(
        "/api/projects",
        json={
            "name": "Vector Index Demo",
            "root_path": str(project_root),
        },
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    if scan:
        scan_response = client.post(f"/api/projects/{project_id}/scan")
        assert scan_response.status_code == 200
    return project_id


def test_build_vector_index_endpoint(
    client,
    tmp_path,
    fake_retrieval_dependencies,
) -> None:
    project_id = create_project(client, tmp_path, scan=True)
    fake_embeddings, fake_store = fake_retrieval_dependencies

    response = client.post(
        f"/api/projects/{project_id}/build-vector-index"
    )

    assert response.status_code == 200
    assert response.json() == {
        "project_id": project_id,
        "collection_name": f"project_{project_id}_code_chunks",
        "chunks_indexed": 13,
    }
    assert fake_store.project_id == project_id
    assert len(fake_store.chunks) == 13
    assert len(fake_store.vectors) == 13
    assert fake_embeddings.document_texts == [
        chunk.searchable_text for chunk in fake_store.chunks
    ]


def test_build_vector_index_returns_project_not_found(client) -> None:
    response = client.post("/api/projects/99999/build-vector-index")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_build_vector_index_rejects_unscanned_project(
    client,
    tmp_path,
) -> None:
    project_id = create_project(client, tmp_path, scan=False)

    response = client.post(
        f"/api/projects/{project_id}/build-vector-index"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROJECT_NOT_SCANNED"
