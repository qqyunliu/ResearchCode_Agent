import argparse

from qdrant_client import QdrantClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import CodeEntity
from app.retrieval.chunk_builder import CodeChunkBuilder
from app.retrieval.embedding_service import (
    EmbeddingService,
    LocalSentenceTransformerProvider,
)
from app.retrieval.vector_store import QdrantVectorStore


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description=(
            "Build an in-memory Qdrant index and search one project."
        )
    )
    argument_parser.add_argument("project_id", type=int)
    argument_parser.add_argument("query")
    argument_parser.add_argument("--limit", type=int, default=5)
    args = argument_parser.parse_args()

    if args.limit < 1:
        argument_parser.error("--limit must be greater than zero")

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

    settings = get_settings()
    chunks = CodeChunkBuilder(
        settings.chunk_max_content_chars
    ).build_many(entities)
    embeddings = EmbeddingService(
        LocalSentenceTransformerProvider(settings.embedding_model)
    )
    vectors = embeddings.embed_documents(
        [chunk.searchable_text for chunk in chunks]
    )

    store = QdrantVectorStore(QdrantClient(":memory:"))
    store.rebuild(args.project_id, chunks, vectors)
    hits = store.search(
        args.project_id,
        embeddings.embed_query(args.query),
        args.limit,
    )

    print(
        f"Indexed {len(chunks)} chunks into "
        f"{store.collection_name(args.project_id)}"
    )
    print(f"Query: {args.query}")
    print(f"Hits: {len(hits)}")
    for rank, hit in enumerate(hits, start=1):
        print(
            f"{rank}. score={hit.score:.4f} "
            f"{hit.entity_type} {hit.qualified_name}"
        )
        print(
            f"   {hit.file_path}:{hit.start_line}-{hit.end_line}"
        )


if __name__ == "__main__":
    main()
