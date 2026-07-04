import argparse
import math
import platform
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import CodeEntity
from app.retrieval.chunk_builder import CodeChunkBuilder
from app.retrieval.embedding_service import (
    EmbeddingService,
    LocalSentenceTransformerProvider,
)


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Benchmark local CPU embeddings for indexed code entities."
    )
    argument_parser.add_argument("project_id", type=int)
    args = argument_parser.parse_args()

    settings = get_settings()
    with SessionLocal() as session:
        entities = session.scalars(
            select(CodeEntity)
            .where(CodeEntity.project_id == args.project_id)
            .order_by(CodeEntity.id)
        ).all()
    if not entities:
        argument_parser.error(
            f"project {args.project_id} has no indexed entities"
        )

    chunks = CodeChunkBuilder(
        settings.chunk_max_content_chars
    ).build_many(entities)
    service = EmbeddingService(
        LocalSentenceTransformerProvider(settings.embedding_model)
    )

    print(f"Platform: {platform.platform()}")
    print(f"Model: {settings.embedding_model}")
    print(f"Chunks: {len(chunks)}")
    print("Device: CPU")

    documents_started = time.perf_counter()
    vectors = service.embed_documents(
        [chunk.searchable_text for chunk in chunks]
    )
    documents_elapsed = time.perf_counter() - documents_started

    query_started = time.perf_counter()
    query_vector = service.embed_query(
        "Where is the alert API implemented?"
    )
    query_elapsed = time.perf_counter() - query_started

    document_norm = math.sqrt(sum(value * value for value in vectors[0]))
    query_norm = math.sqrt(
        sum(value * value for value in query_vector)
    )
    print(f"Vector dimension: {len(query_vector)}")
    print(
        "First document batch "
        f"(download/load/encode): {documents_elapsed:.3f}s"
    )
    print(f"Warm single query: {query_elapsed:.3f}s")
    print(f"First document norm: {document_norm:.6f}")
    print(f"Query norm: {query_norm:.6f}")


if __name__ == "__main__":
    main()
