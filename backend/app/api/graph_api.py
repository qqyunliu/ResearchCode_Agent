from typing import Protocol

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.dependencies import get_embedding_service, get_vector_store, get_query_rewriter
from app.retrieval.query_rewriter import LlmQueryRewriter
from app.graph.query_service import GraphQueryService
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.hybrid_search import HybridSearchService
from app.retrieval.keyword_search import KeywordSearchService
from app.retrieval.types import SearchHit
from app.retrieval.vector_store import QdrantVectorStore
from app.schemas.graph import GraphResponse, SearchChainRequest

router = APIRouter()


class GraphSearch(Protocol):
    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]: ...


def get_graph_search_service(
    session: Session = Depends(get_session),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
    rewriter: LlmQueryRewriter = Depends(get_query_rewriter),
) -> GraphSearch:
    return HybridSearchService(
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=KeywordSearchService(session),
        rewriter=rewriter,
    )


@router.get("/api-chain", response_model=GraphResponse)
def api_chain(
    project_id: int,
    method: str = Query(min_length=1),
    api_path: str = Query(min_length=1),
    session: Session = Depends(get_session),
) -> GraphResponse:
    result = GraphQueryService(session).find_api_chain(
        project_id,
        method,
        api_path,
    )
    return GraphResponse.from_result(result)


@router.post("/search-chain", response_model=GraphResponse)
def search_chain(
    data: SearchChainRequest,
    session: Session = Depends(get_session),
    search: GraphSearch = Depends(get_graph_search_service),
) -> GraphResponse:
    hits = search.search(data.project_id, data.query, data.limit)
    result = GraphQueryService(session).expand_entities(
        data.project_id,
        (hit.entity_id for hit in hits),
        max_depth=data.max_depth,
    )
    return GraphResponse.from_result(result)
