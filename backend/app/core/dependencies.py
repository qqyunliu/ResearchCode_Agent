from functools import lru_cache

from qdrant_client import QdrantClient

from app.agent.planner import SimpleAgentPlanner
from app.core.config import get_settings
from app.llm.client import OpenAICompatibleLlmClient
from app.rag.context_builder import RagContextBuilder
from app.rag.graph_context_builder import GraphContextBuilder
from app.retrieval.chunk_builder import CodeChunkBuilder
from app.retrieval.embedding_service import (
    EmbeddingService,
    LocalSentenceTransformerProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.retrieval.vector_store import QdrantVectorStore


@lru_cache
def get_chunk_builder() -> CodeChunkBuilder:
    settings = get_settings()
    return CodeChunkBuilder(settings.chunk_max_content_chars)


@lru_cache
def get_embedding_service() -> EmbeddingService:
    settings = get_settings()
    if settings.embedding_provider == "local":
        provider = LocalSentenceTransformerProvider(
            settings.embedding_model
        )
    elif settings.embedding_provider == "api":
        provider = OpenAICompatibleEmbeddingProvider(
            settings.embedding_model,
            settings.embedding_api_key,
            base_url=settings.embedding_base_url,
        )
    else:
        raise ValueError(
            "RCA_EMBEDDING_PROVIDER must be 'local' or 'api'"
        )
    return EmbeddingService(provider)


@lru_cache
def get_vector_store() -> QdrantVectorStore:
    settings = get_settings()
    if settings.qdrant_url:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
    else:
        client = QdrantClient(path=settings.qdrant_path)
    return QdrantVectorStore(client)


@lru_cache
def get_llm_client() -> OpenAICompatibleLlmClient:
    settings = get_settings()
    return OpenAICompatibleLlmClient(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


@lru_cache
def get_rag_context_builder() -> RagContextBuilder:
    return RagContextBuilder(get_settings().rag_max_context_chars)


@lru_cache
def get_graph_context_builder() -> GraphContextBuilder:
    return GraphContextBuilder(get_settings().rag_max_context_chars)


@lru_cache
def get_agent_planner() -> SimpleAgentPlanner:
    return SimpleAgentPlanner()
