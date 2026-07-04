import argparse

from app.rag.context_builder import RagContextBuilder
from app.retrieval.types import SearchHit


def sample_hits() -> list[SearchHit]:
    return [
        SearchHit(
            entity_id=5,
            entity_type="java_method",
            name="getAlert",
            qualified_name="AlertController.getAlert",
            file_path="backend/src/AlertController.java",
            start_line=4,
            end_line=7,
            content=(
                '@GetMapping("/{id}")\n'
                "Alert getAlert(Long id) {\n"
                "    return null;\n"
                "}"
            ),
            metadata={},
            score=1.0,
            source="hybrid",
        ),
        SearchHit(
            entity_id=6,
            entity_type="backend_api",
            name="GET /api/alerts/{id}",
            qualified_name="GET /api/alerts/{id}",
            file_path="backend/src/AlertController.java",
            start_line=4,
            end_line=7,
            content='@GetMapping("/{id}")',
            metadata={"http_method": "GET"},
            score=0.72,
            source="hybrid",
        ),
    ]


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Show bounded RAG context and structured references."
    )
    argument_parser.add_argument(
        "--max-context-chars",
        type=int,
        default=12000,
    )
    args = argument_parser.parse_args()

    context = RagContextBuilder(args.max_context_chars).build(
        sample_hits()
    )
    print("=== Context sent to the LLM ===")
    print(context.text or "(empty)")
    print("\n=== Structured references ===")
    for reference in context.references:
        print(
            f"[{reference.citation}] entity={reference.entity_id} "
            f"{reference.file_path}:"
            f"{reference.start_line}-{reference.end_line} "
            f"{reference.qualified_name}"
        )
    print(
        f"\nCharacters: {len(context.text)}/"
        f"{args.max_context_chars}"
    )


if __name__ == "__main__":
    main()
