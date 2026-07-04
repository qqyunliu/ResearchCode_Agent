from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import CodeEntity, Project
from app.retrieval.chunk_builder import CodeChunkBuilder
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.vector_store import QdrantVectorStore
from app.schemas.retrieval import VectorIndexSummary


class VectorIndexService:
    def __init__(
        self,
        session: Session,
        *,
        chunk_builder: CodeChunkBuilder,
        embeddings: EmbeddingService,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.session = session
        self.chunk_builder = chunk_builder
        self.embeddings = embeddings
        self.vector_store = vector_store

    def build(self, project_id: int) -> VectorIndexSummary:
        project = self.session.get(Project, project_id)
        if project is None:
            raise DomainError(
                code="PROJECT_NOT_FOUND",
                message=f"Project {project_id} does not exist.",
                status_code=404,
            )

        entities = list(
            self.session.scalars(
                select(CodeEntity)
                .where(CodeEntity.project_id == project_id)
                .order_by(CodeEntity.id)
            ).all()
        )
        if not entities:
            raise DomainError(
                code="PROJECT_NOT_SCANNED",
                message=f"Project {project_id} has no indexed entities.",
                status_code=409,
            )

        chunks = self.chunk_builder.build_many(entities)
        vectors = self.embeddings.embed_documents(
            [chunk.searchable_text for chunk in chunks]
        )
        self.vector_store.rebuild(project_id, chunks, vectors)

        return VectorIndexSummary(
            project_id=project_id,
            collection_name=self.vector_store.collection_name(project_id),
            chunks_indexed=len(chunks),
        )
