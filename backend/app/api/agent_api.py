from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.dependencies import (
    get_embedding_service,
    get_llm_client,
    get_rag_context_builder,
    get_vector_store,
)
from app.llm.client import LlmClient
from app.rag.context_builder import RagContextBuilder
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.hybrid_search import HybridSearchService
from app.retrieval.keyword_search import KeywordSearchService
from app.retrieval.vector_store import QdrantVectorStore
from app.schemas.agent import CodeQaRequest, CodeQaResponse
from app.services.code_qa_service import CodeQaService

router = APIRouter()


def get_code_qa_service(
    session: Session = Depends(get_session),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
    context_builder: RagContextBuilder = Depends(get_rag_context_builder),
    llm: LlmClient = Depends(get_llm_client),
) -> CodeQaService:
    search = HybridSearchService(
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=KeywordSearchService(session),
    )
    return CodeQaService(
        search=search,
        context_builder=context_builder,
        llm=llm,
    )


@router.post("/code-qa", response_model=CodeQaResponse)
def answer_code_question(
    data: CodeQaRequest,
    service: CodeQaService = Depends(get_code_qa_service),
) -> CodeQaResponse:
    return service.answer(
        project_id=data.project_id,
        question=data.question,
        limit=data.limit,
    )
