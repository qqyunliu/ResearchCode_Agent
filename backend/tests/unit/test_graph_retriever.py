from app.graph.types import GraphEdge, GraphNode, GraphResult
from app.rag.graph_retriever import (
    CHAIN_RELATION_TYPES,
    GraphRagRetriever,
)
from app.retrieval.types import SearchHit


def hit(entity_id: int, score: float) -> SearchHit:
    return SearchHit(
        entity_id=entity_id,
        entity_type="java_method",
        name=f"method{entity_id}",
        qualified_name=f"Demo.method{entity_id}",
        file_path="src/Demo.java",
        start_line=entity_id,
        end_line=entity_id,
        content=f"method {entity_id}",
        metadata={"direct": True},
        score=score,
        source="hybrid",
    )


def node(entity_id: int) -> GraphNode:
    return GraphNode(
        entity_id=entity_id,
        label=f"Demo.method{entity_id}",
        entity_type="java_method",
        qualified_name=f"Demo.method{entity_id}",
        file_path="src/Demo.java",
        start_line=entity_id,
        end_line=entity_id,
        content=f"method {entity_id}",
        metadata={"graph": True},
    )


def edge(
    relation_id: int,
    source_id: int,
    target_id: int,
    relation_type: str = "CALLS_METHOD",
) -> GraphEdge:
    return GraphEdge(
        relation_id=relation_id,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        confidence=0.8,
        metadata={},
    )


class FakeSearch:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[int, str, int]] = []

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        self.calls.append((project_id, query, limit))
        return self.hits[:limit]


class FakeGraph:
    def __init__(self, results: dict[int, GraphResult]) -> None:
        self.results = results
        self.calls: list[
            tuple[int, int, int, tuple[str, ...] | None]
        ] = []

    def traverse(
        self,
        project_id: int,
        entity_id: int,
        *,
        max_depth: int,
        relation_types: tuple[str, ...] | None,
    ) -> GraphResult:
        self.calls.append(
            (project_id, entity_id, max_depth, relation_types)
        )
        return self.results[entity_id]


def test_ranks_direct_then_one_hop_then_two_hop() -> None:
    search = FakeSearch([hit(1, 0.9)])
    graph = FakeGraph(
        {
            1: GraphResult(
                nodes=(node(1), node(3), node(4)),
                edges=(edge(1, 1, 3), edge(2, 3, 4)),
            )
        }
    )

    results = GraphRagRetriever(
        search=search,
        graph=graph,
    ).retrieve(7, "trace alert", limit=5, max_depth=2)

    assert [result.entity_id for result in results] == [1, 3, 4]
    assert [result.graph_depth for result in results] == [0, 1, 2]
    assert results[0].relation_reason == "direct hybrid-search hit"
    assert (
        results[1].relation_reason
        == "Demo.method1 CALLS_METHOD Demo.method3"
    )
    assert results[2].seed_entity_id == 1
    assert all(result.retrieval_score == 0.9 for result in results)
    assert graph.calls == [(7, 1, 2, CHAIN_RELATION_TYPES)]


def test_same_depth_uses_inherited_score_and_deduplicates() -> None:
    search = FakeSearch([hit(1, 0.9), hit(2, 0.6)])
    graph = FakeGraph(
        {
            1: GraphResult(
                nodes=(node(1), node(3)),
                edges=(edge(1, 1, 3),),
            ),
            2: GraphResult(
                nodes=(node(2), node(3), node(4)),
                edges=(edge(2, 2, 3), edge(3, 2, 4)),
            ),
        }
    )

    results = GraphRagRetriever(
        search=search,
        graph=graph,
    ).retrieve(7, "trace alert", limit=5, max_depth=1)

    assert [result.entity_id for result in results] == [1, 2, 3, 4]
    result_three = next(
        result for result in results if result.entity_id == 3
    )
    assert result_three.seed_entity_id == 1
    assert result_three.retrieval_score == 0.9


def test_direct_hit_replaces_graph_neighbor_version() -> None:
    search = FakeSearch([hit(1, 0.9), hit(3, 0.4)])
    graph = FakeGraph(
        {
            1: GraphResult(
                nodes=(node(1), node(3)),
                edges=(edge(1, 1, 3),),
            ),
            3: GraphResult(nodes=(node(3),), edges=()),
        }
    )

    results = GraphRagRetriever(
        search=search,
        graph=graph,
    ).retrieve(7, "trace alert", limit=5, max_depth=1)

    result_three = next(
        result for result in results if result.entity_id == 3
    )
    assert result_three.graph_depth == 0
    assert result_three.seed_entity_id == 3
    assert result_three.metadata == {"direct": True}


def test_respects_depth_and_result_limits() -> None:
    search = FakeSearch([hit(1, 0.9)])
    graph = FakeGraph(
        {
            1: GraphResult(
                nodes=(node(1), node(2), node(3), node(4)),
                edges=(
                    edge(1, 1, 2),
                    edge(2, 1, 3),
                    edge(3, 2, 4),
                ),
            )
        }
    )

    results = GraphRagRetriever(
        search=search,
        graph=graph,
        max_results=2,
    ).retrieve(7, "trace alert", limit=5, max_depth=1)

    assert [result.entity_id for result in results] == [1, 2]
    assert all(result.graph_depth <= 1 for result in results)


def test_ignores_non_chain_relations_even_if_graph_returns_them() -> None:
    search = FakeSearch([hit(1, 0.9)])
    graph = FakeGraph(
        {
            1: GraphResult(
                nodes=(node(1), node(2), node(3)),
                edges=(
                    edge(1, 1, 2, "CALLS_METHOD"),
                    edge(2, 1, 3, "CONTAINS"),
                ),
            )
        }
    )

    results = GraphRagRetriever(
        search=search,
        graph=graph,
    ).retrieve(7, "trace alert", limit=5, max_depth=1)

    assert [result.entity_id for result in results] == [1, 2]


def test_empty_search_returns_no_graph_results() -> None:
    search = FakeSearch([])
    graph = FakeGraph({})

    results = GraphRagRetriever(
        search=search,
        graph=graph,
    ).retrieve(7, "missing", limit=5, max_depth=2)

    assert results == []
    assert graph.calls == []


def test_graph_failure_keeps_direct_hits_with_uncertainty() -> None:
    class FailingGraph:
        def traverse(
            self,
            project_id,
            entity_id,
            *,
            max_depth,
            relation_types,
        ):
            raise TimeoutError("sqlite graph query timed out")

    results = GraphRagRetriever(
        search=FakeSearch([hit(1, 0.9)]),
        graph=FailingGraph(),
    ).retrieve(7, "trace alert", limit=5, max_depth=2)

    assert [result.entity_id for result in results] == [1]
    assert results[0].graph_depth == 0
    assert results[0].uncertainties == (
        (
            "Graph relationship retrieval was unavailable; "
            "only direct search evidence was used."
        ),
    )
