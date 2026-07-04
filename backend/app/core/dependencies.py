from functools import lru_cache

from qdrant_client import QdrantClient

from app.core.config import get_settings
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
