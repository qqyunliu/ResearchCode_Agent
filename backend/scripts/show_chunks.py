import argparse

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import CodeEntity
from app.retrieval.chunk_builder import CodeChunkBuilder


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Print deterministic retrieval chunks for one project."
    )
    argument_parser.add_argument("project_id", type=int)
    argument_parser.add_argument("--limit", type=int, default=3)
    argument_parser.add_argument(
        "--max-content-chars",
        type=int,
        default=4000,
    )
    args = argument_parser.parse_args()

    if args.limit < 1:
        argument_parser.error("--limit must be greater than zero")

    with SessionLocal() as session:
        entities = session.scalars(
            select(CodeEntity)
            .where(CodeEntity.project_id == args.project_id)
            .order_by(CodeEntity.id)
            .limit(args.limit)
        ).all()

    chunks = CodeChunkBuilder(
        max_content_chars=args.max_content_chars
    ).build_many(entities)
    print(f"Chunks: {len(chunks)}")
    for chunk in chunks:
        print(f"\n--- {chunk.chunk_id} ---")
        print(
            f"Reference: {chunk.file_path}:"
            f"{chunk.start_line}-{chunk.end_line}"
        )
        print(chunk.searchable_text)


if __name__ == "__main__":
    main()
