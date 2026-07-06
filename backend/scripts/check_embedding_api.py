import math

from app.core.config import get_settings
from app.retrieval.embedding_service import (
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)

TEXTS = (
    "告警列表接口",
    "alert list API",
    "database migration rollback",
)


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(
        sum(b * b for b in right)
    )
    if denominator == 0:
        raise ValueError("embedding vector must be non-zero")
    return numerator / denominator


def check(provider: EmbeddingProvider, dimensions: int) -> tuple[float, float]:
    vectors = provider.embed_documents(list(TEXTS))
    if len(vectors) != 3 or any(len(item) != dimensions for item in vectors):
        raise ValueError("embedding response has unexpected shape")
    related = cosine(vectors[0], vectors[1])
    unrelated = cosine(vectors[0], vectors[2])
    if related <= unrelated:
        raise ValueError("cross-language similarity check failed")
    return related, unrelated


def main() -> None:
    settings = get_settings()
    if settings.embedding_provider != "api":
        raise ValueError("RCA_EMBEDDING_PROVIDER must be api")
    if settings.embedding_model != "embedding-3":
        raise ValueError("RCA_EMBEDDING_MODEL must be embedding-3")
    if settings.embedding_dimensions != 1024:
        raise ValueError("RCA_EMBEDDING_DIMENSIONS must be 1024")
    provider = OpenAICompatibleEmbeddingProvider(
        settings.embedding_model,
        settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimensions,
    )
    related, unrelated = check(provider, settings.embedding_dimensions)
    print("model=embedding-3 vectors=3 dimensions=1024")
    print(f"related_similarity={related:.6f}")
    print(f"unrelated_similarity={unrelated:.6f}")


if __name__ == "__main__":
    main()
