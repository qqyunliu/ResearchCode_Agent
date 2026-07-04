from collections.abc import Sequence
from dataclasses import dataclass

from app.retrieval.types import SearchHit


@dataclass(frozen=True, slots=True)
class ContextReference:
    citation: int
    entity_id: int
    file_path: str
    start_line: int
    end_line: int
    entity_type: str
    qualified_name: str


@dataclass(frozen=True, slots=True)
class RagContext:
    text: str
    references: Sequence[ContextReference]


class RagContextBuilder:
    def __init__(self, max_context_chars: int = 12000) -> None:
        if max_context_chars < 1:
            raise ValueError(
                "max_context_chars must be greater than zero"
            )
        self.max_context_chars = max_context_chars

    def build(self, hits: Sequence[SearchHit]) -> RagContext:
        blocks: list[str] = []
        references: list[ContextReference] = []
        current_length = 0

        for citation, hit in enumerate(hits, start=1):
            block = self._block(citation, hit)
            separator_length = 2 if blocks else 0
            next_length = current_length + separator_length + len(block)
            if next_length > self.max_context_chars:
                break

            blocks.append(block)
            references.append(self._reference(citation, hit))
            current_length = next_length

        return RagContext(
            text="\n\n".join(blocks),
            references=tuple(references),
        )

    @staticmethod
    def _block(citation: int, hit: SearchHit) -> str:
        return "\n".join(
            [
                (
                    f"[{citation}] {hit.file_path}:"
                    f"{hit.start_line}-{hit.end_line}"
                ),
                f"Type: {hit.entity_type}",
                f"Name: {hit.qualified_name}",
                "Code:",
                hit.content,
            ]
        )

    @staticmethod
    def _reference(
        citation: int,
        hit: SearchHit,
    ) -> ContextReference:
        return ContextReference(
            citation=citation,
            entity_id=hit.entity_id,
            file_path=hit.file_path,
            start_line=hit.start_line,
            end_line=hit.end_line,
            entity_type=hit.entity_type,
            qualified_name=hit.qualified_name,
        )
