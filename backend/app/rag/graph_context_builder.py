from collections.abc import Sequence

from app.graph.types import GraphResult
from app.rag.context_builder import ContextReference, RagContext
from app.rag.graph_retriever import GraphRetrievalResult


class GraphContextBuilder:
    def __init__(self, max_context_chars: int = 12000) -> None:
        if max_context_chars < 1:
            raise ValueError(
                "max_context_chars must be greater than zero"
            )
        self.max_context_chars = max_context_chars

    def build(
        self,
        results: Sequence[GraphRetrievalResult],
        graph: GraphResult,
    ) -> RagContext:
        if not results:
            return RagContext(text="", references=())

        sections: list[str] = []
        references: list[ContextReference] = []
        included_ids: set[int] = set()
        current_length = 0
        for result in results:
            citation = len(references) + 1
            block = self._node_block(citation, result)
            next_length = self._next_length(
                current_length,
                block,
                bool(sections),
            )
            if next_length > self.max_context_chars:
                continue
            sections.append(block)
            references.append(self._reference(citation, result))
            included_ids.add(result.entity_id)
            current_length = next_length

        edge_section = self._edge_section(graph, included_ids)
        if edge_section:
            next_length = self._next_length(
                current_length,
                edge_section,
                bool(sections),
            )
            if next_length <= self.max_context_chars:
                sections.append(edge_section)

        return RagContext(
            text="\n\n".join(sections),
            references=tuple(references),
        )

    @staticmethod
    def _node_block(
        citation: int,
        result: GraphRetrievalResult,
    ) -> str:
        return "\n".join(
            [
                (
                    f"[{citation}] {result.file_path}:"
                    f"{result.start_line}-{result.end_line}"
                ),
                f"Type: {result.entity_type}",
                f"Name: {result.qualified_name}",
                f"Retrieval score: {result.retrieval_score}",
                f"Graph depth: {result.graph_depth}",
                f"Relation reason: {result.relation_reason}",
                "Code:",
                result.content,
            ]
        )

    @staticmethod
    def _edge_section(
        graph: GraphResult,
        included_ids: set[int],
    ) -> str:
        nodes = {node.entity_id: node for node in graph.nodes}
        lines = []
        for edge in graph.edges:
            if (
                edge.source_id not in included_ids
                or edge.target_id not in included_ids
                or edge.source_id not in nodes
                or edge.target_id not in nodes
            ):
                continue
            source = nodes[edge.source_id]
            target = nodes[edge.target_id]
            lines.append(
                f"{source.qualified_name} "
                f"-[{edge.relation_type} "
                f"confidence={edge.confidence}]-> "
                f"{target.qualified_name}"
            )
        if not lines:
            return ""
        return "\n".join(
            ["Stored graph edges (authoritative):", *lines]
        )

    @staticmethod
    def _reference(
        citation: int,
        result: GraphRetrievalResult,
    ) -> ContextReference:
        return ContextReference(
            citation=citation,
            entity_id=result.entity_id,
            file_path=result.file_path,
            start_line=result.start_line,
            end_line=result.end_line,
            entity_type=result.entity_type,
            qualified_name=result.qualified_name,
        )

    @staticmethod
    def _next_length(
        current_length: int,
        section: str,
        has_sections: bool,
    ) -> int:
        return current_length + (2 if has_sections else 0) + len(section)
