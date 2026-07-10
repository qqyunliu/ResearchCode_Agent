from collections import deque
from dataclasses import dataclass, replace
from typing import Protocol

from app.graph.types import GraphEdge, GraphNode, GraphResult
from app.retrieval.types import SearchHit

CHAIN_RELATION_TYPES = (
    "REQUESTS_API",
    "DEFINES_API",
    "CALLS_METHOD",
)
GRAPH_RETRIEVAL_UNCERTAINTY = (
    "Graph relationship retrieval was unavailable; "
    "only direct search evidence was used."
)


@dataclass(frozen=True, slots=True)
class GraphRetrievalResult:
    entity_id: int
    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]
    retrieval_score: float
    graph_depth: int
    relation_reason: str
    seed_entity_id: int
    uncertainties: tuple[str, ...] = ()


class CodeSearch(Protocol):
    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]: ...


class GraphTraversal(Protocol):
    def traverse(
        self,
        project_id: int,
        entity_id: int,
        *,
        max_depth: int,
        relation_types: tuple[str, ...] | None,
    ) -> GraphResult: ...


class GraphRagRetriever:
    def __init__(
        self,
        *,
        search: CodeSearch,
        graph: GraphTraversal,
        max_results: int = 30,
    ) -> None:
        if max_results < 1:
            raise ValueError("max_results must be positive")
        self.search = search
        self.graph = graph
        self.max_results = max_results

    def retrieve(
        self,
        project_id: int,
        query: str,
        *,
        limit: int,
        max_depth: int,
    ) -> list[GraphRetrievalResult]:
        if max_depth < 0 or max_depth > 2:
            raise ValueError("max_depth must be between 0 and 2")
        hits = self.search.search(project_id, query, limit)
        results_by_entity: dict[int, GraphRetrievalResult] = {
            hit.entity_id: self._direct_result(hit) for hit in hits
        }

        for hit in hits:
            try:
                graph_result = self.graph.traverse(
                    project_id,
                    hit.entity_id,
                    max_depth=max_depth,
                    relation_types=CHAIN_RELATION_TYPES,
                )
            except Exception:
                direct = results_by_entity[hit.entity_id]
                results_by_entity[hit.entity_id] = replace(
                    direct,
                    uncertainties=tuple(
                        dict.fromkeys(
                            (
                                *direct.uncertainties,
                                GRAPH_RETRIEVAL_UNCERTAINTY,
                            )
                        )
                    ),
                )
                continue
            for candidate in self._expand(hit, graph_result, max_depth):
                current = results_by_entity.get(candidate.entity_id)
                if current is None or self._rank(candidate) < self._rank(
                    current
                ):
                    results_by_entity[candidate.entity_id] = candidate

        return sorted(
            results_by_entity.values(),
            key=self._rank,
        )[: self.max_results]

    @staticmethod
    def _direct_result(hit: SearchHit) -> GraphRetrievalResult:
        return GraphRetrievalResult(
            entity_id=hit.entity_id,
            entity_type=hit.entity_type,
            name=hit.name,
            qualified_name=hit.qualified_name,
            file_path=hit.file_path,
            start_line=hit.start_line,
            end_line=hit.end_line,
            content=hit.content,
            metadata=hit.metadata,
            retrieval_score=hit.score,
            graph_depth=0,
            relation_reason="direct hybrid-search hit",
            seed_entity_id=hit.entity_id,
            uncertainties=hit.uncertainties,
        )

    @classmethod
    def _expand(
        cls,
        hit: SearchHit,
        graph: GraphResult,
        max_depth: int,
    ) -> list[GraphRetrievalResult]:
        nodes = {node.entity_id: node for node in graph.nodes}
        if hit.entity_id not in nodes:
            return []
        adjacency: dict[int, list[tuple[int, GraphEdge]]] = {}
        for edge in graph.edges:
            if edge.relation_type not in CHAIN_RELATION_TYPES:
                continue
            adjacency.setdefault(edge.source_id, []).append(
                (edge.target_id, edge)
            )
            adjacency.setdefault(edge.target_id, []).append(
                (edge.source_id, edge)
            )
        for neighbors in adjacency.values():
            neighbors.sort(key=lambda item: (item[0], item[1].relation_id))

        queue = deque([(hit.entity_id, 0)])
        visited = {hit.entity_id}
        expanded: list[GraphRetrievalResult] = []
        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor_id, edge in adjacency.get(current_id, []):
                if neighbor_id in visited or neighbor_id not in nodes:
                    continue
                visited.add(neighbor_id)
                neighbor_depth = depth + 1
                queue.append((neighbor_id, neighbor_depth))
                neighbor = nodes[neighbor_id]
                expanded.append(
                    GraphRetrievalResult(
                        entity_id=neighbor.entity_id,
                        entity_type=neighbor.entity_type,
                        name=neighbor.label,
                        qualified_name=neighbor.qualified_name,
                        file_path=neighbor.file_path,
                        start_line=neighbor.start_line,
                        end_line=neighbor.end_line,
                        content=neighbor.content,
                        metadata=neighbor.metadata,
                        retrieval_score=hit.score,
                        graph_depth=neighbor_depth,
                        relation_reason=cls._reason(edge, nodes),
                        seed_entity_id=hit.entity_id,
                        uncertainties=hit.uncertainties,
                    )
                )
        return expanded

    @staticmethod
    def _reason(
        edge: GraphEdge,
        nodes: dict[int, GraphNode],
    ) -> str:
        source = nodes[edge.source_id]
        target = nodes[edge.target_id]
        return (
            f"{source.qualified_name} {edge.relation_type} "
            f"{target.qualified_name}"
        )

    @staticmethod
    def _rank(result: GraphRetrievalResult) -> tuple[int, float, int, int]:
        return (
            result.graph_depth,
            -result.retrieval_score,
            result.entity_id,
            result.seed_entity_id,
        )
