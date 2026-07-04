from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.dependencies import (
    get_chunk_builder,
    get_embedding_service,
    get_vector_store,
)
from app.retrieval.chunk_builder import CodeChunkBuilder
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.vector_store import QdrantVectorStore
from app.schemas.retrieval import VectorIndexSummary
from app.services.vector_index_service import VectorIndexService

router = APIRouter()


@router.post(
    "/projects/{project_id}/build-vector-index",
    response_model=VectorIndexSummary,
)
def build_vector_index(
    project_id: int,
    session: Session = Depends(get_session),
    chunk_builder: CodeChunkBuilder = Depends(get_chunk_builder),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
) -> VectorIndexSummary:
    return VectorIndexService(
        session,
        chunk_builder=chunk_builder,
        embeddings=embeddings,
        vector_store=vector_store,
    ).build(project_id)
