import uuid
from collections.abc import Sequence

from qdrant_client import QdrantClient, models

from app.retrieval.types import CodeChunk, SearchHit


class QdrantVectorStore:
    def __init__(self, client: QdrantClient) -> None:
        self._client = client

    @staticmethod
    def collection_name(project_id: int) -> str:
        return f"project_{project_id}_code_chunks"

    def rebuild(
        self,
        project_id: int,
        chunks: Sequence[CodeChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        dimension = self._validate_rebuild_input(chunks, vectors)
        collection_name = self.collection_name(project_id)

        if self._client.collection_exists(collection_name):
            self._client.delete_collection(collection_name)

        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )
        self._client.upsert(
            collection_name=collection_name,
            points=[
                models.PointStruct(
                    id=self._point_id(project_id, chunk.chunk_id),
                    vector=list(vector),
                    payload=self._payload(chunk),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
            wait=True,
        )

    def search(
        self,
        project_id: int,
        query_vector: Sequence[float],
        limit: int,
    ) -> list[SearchHit]:
        collection_name = self.collection_name(project_id)
        if not self._client.collection_exists(collection_name):
            return []

        response = self._client.query_points(
            collection_name=collection_name,
            query=list(query_vector),
            with_payload=True,
            limit=limit,
        )
        return [
            self._search_hit(point.payload or {}, point.score)
            for point in response.points
        ]

    @staticmethod
    def _validate_rebuild_input(
        chunks: Sequence[CodeChunk],
        vectors: Sequence[Sequence[float]],
    ) -> int:
        if not chunks or not vectors:
            if len(chunks) != len(vectors):
                raise ValueError("chunks and vectors must have the same length")
            raise ValueError("chunks and vectors must not be empty")
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")

        dimension = len(vectors[0])
        if dimension == 0:
            raise ValueError("vectors must not be empty")
        if any(len(vector) != dimension for vector in vectors):
            raise ValueError("vectors must have the same dimension")
        return dimension

    @staticmethod
    def _point_id(project_id: int, chunk_id: str) -> str:
        identity = f"research-code-agent:{project_id}:{chunk_id}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))

    @staticmethod
    def _payload(chunk: CodeChunk) -> dict[str, object]:
        return {
            "entity_id": chunk.entity_id,
            "entity_key": chunk.entity_key,
            "entity_type": chunk.entity_type,
            "name": chunk.name,
            "qualified_name": chunk.qualified_name,
            "file_path": chunk.file_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "content": chunk.content,
            "metadata": chunk.metadata,
        }

    @staticmethod
    def _search_hit(
        payload: dict[str, object],
        score: float,
    ) -> SearchHit:
        return SearchHit(
            entity_id=int(payload["entity_id"]),
            entity_type=str(payload["entity_type"]),
            name=str(payload["name"]),
            qualified_name=str(payload["qualified_name"]),
            file_path=str(payload["file_path"]),
            start_line=int(payload["start_line"]),
            end_line=int(payload["end_line"]),
            content=str(payload["content"]),
            metadata=dict(payload["metadata"]),
            score=score,
            source="vector",
        )
