from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.dependencies import (
    get_chunk_builder,
    get_embedding_service,
    get_vector_store,
    get_query_rewriter,
)
from app.retrieval.chunk_builder import CodeChunkBuilder
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.hybrid_search import HybridSearchService
from app.retrieval.keyword_search import KeywordSearchService
from app.retrieval.vector_store import QdrantVectorStore
from app.retrieval.query_rewriter import LlmQueryRewriter
from app.schemas.retrieval import (
    SearchHitRead,
    SearchRequest,
    VectorIndexSummary,
)
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


@router.post(
    "/search/keyword",
    response_model=list[SearchHitRead],
)
def keyword_search(
    data: SearchRequest,
    session: Session = Depends(get_session),
) -> list[SearchHitRead]:
    return KeywordSearchService(session).search(
        data.project_id,
        data.query,
        data.limit,
    )


@router.post(
    "/search/hybrid",
    response_model=list[SearchHitRead],
)
def hybrid_search(
    data: SearchRequest,
    session: Session = Depends(get_session),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
    rewriter: LlmQueryRewriter = Depends(get_query_rewriter),
) -> list[SearchHitRead]:
    return HybridSearchService(
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=KeywordSearchService(session),
        rewriter=rewriter,
    ).search(
        data.project_id,
        data.query,
        data.limit,
    )
