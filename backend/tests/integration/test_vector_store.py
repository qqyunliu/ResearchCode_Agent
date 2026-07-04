import pytest
from qdrant_client import QdrantClient

from app.retrieval.types import CodeChunk
from app.retrieval.vector_store import QdrantVectorStore


def chunk(entity_id: int, name: str) -> CodeChunk:
    return CodeChunk(
        chunk_id=f"entity:{entity_id}",
        entity_id=entity_id,
        entity_key=f"java_method:src/Demo.java:{name}:{entity_id}",
        entity_type="java_method",
        name=name,
        qualified_name=f"Demo.{name}",
        file_path="src/Demo.java",
        start_line=entity_id,
        end_line=entity_id + 2,
        content=f"void {name}() {{}}",
        metadata={"language": "java"},
        searchable_text=f"Method named {name}",
    )


def test_rebuild_and_search_project_collection() -> None:
    alert_chunk = chunk(1, "getAlert")
    device_chunk = chunk(2, "getDevice")
    store = QdrantVectorStore(QdrantClient(":memory:"))

    store.rebuild(
        project_id=3,
        chunks=[alert_chunk, device_chunk],
        vectors=[[1.0, 0.0], [0.0, 1.0]],
    )
    hits = store.search(
        project_id=3,
        query_vector=[0.9, 0.1],
        limit=1,
    )

    assert len(hits) == 1
    assert hits[0].entity_id == alert_chunk.entity_id
    assert hits[0].qualified_name == "Demo.getAlert"
    assert hits[0].metadata == {"language": "java"}
    assert hits[0].source == "vector"
    assert hits[0].score > 0.9


def test_rebuild_replaces_old_points() -> None:
    store = QdrantVectorStore(QdrantClient(":memory:"))
    store.rebuild(
        project_id=3,
        chunks=[chunk(1, "oldMethod")],
        vectors=[[1.0, 0.0]],
    )

    store.rebuild(
        project_id=3,
        chunks=[chunk(2, "newMethod")],
        vectors=[[0.0, 1.0]],
    )

    hits = store.search(
        project_id=3,
        query_vector=[1.0, 0.0],
        limit=10,
    )
    assert [hit.name for hit in hits] == ["newMethod"]


def test_projects_use_separate_collections() -> None:
    store = QdrantVectorStore(QdrantClient(":memory:"))
    store.rebuild(
        project_id=3,
        chunks=[chunk(1, "projectThree")],
        vectors=[[1.0, 0.0]],
    )
    store.rebuild(
        project_id=4,
        chunks=[chunk(2, "projectFour")],
        vectors=[[1.0, 0.0]],
    )

    project_three_hits = store.search(
        project_id=3,
        query_vector=[1.0, 0.0],
        limit=10,
    )
    project_four_hits = store.search(
        project_id=4,
        query_vector=[1.0, 0.0],
        limit=10,
    )

    assert [hit.name for hit in project_three_hits] == ["projectThree"]
    assert [hit.name for hit in project_four_hits] == ["projectFour"]


@pytest.mark.parametrize(
    ("chunks", "vectors", "message"),
    [
        ([], [], "must not be empty"),
        ([chunk(1, "one")], [], "same length"),
        (
            [chunk(1, "one"), chunk(2, "two")],
            [[1.0, 0.0], [1.0]],
            "same dimension",
        ),
    ],
)
def test_rebuild_rejects_invalid_chunk_vector_pairs(
    chunks: list[CodeChunk],
    vectors: list[list[float]],
    message: str,
) -> None:
    store = QdrantVectorStore(QdrantClient(":memory:"))

    with pytest.raises(ValueError, match=message):
        store.rebuild(project_id=3, chunks=chunks, vectors=vectors)


def test_search_missing_project_collection_returns_empty_list() -> None:
    store = QdrantVectorStore(QdrantClient(":memory:"))

    assert store.search(
        project_id=404,
        query_vector=[1.0, 0.0],
        limit=10,
    ) == []
