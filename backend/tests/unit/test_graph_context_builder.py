from app.graph.types import GraphEdge, GraphNode, GraphResult
from app.rag.graph_context_builder import GraphContextBuilder
from app.rag.graph_retriever import GraphRetrievalResult


def result(entity_id: int, content: str) -> GraphRetrievalResult:
    return GraphRetrievalResult(
        entity_id=entity_id,
        entity_type="java_method",
        name=f"Demo.method{entity_id}",
        qualified_name=f"Demo.method{entity_id}",
        file_path=f"src/Demo{entity_id}.java",
        start_line=entity_id,
        end_line=entity_id + 1,
        content=content,
        metadata={},
        retrieval_score=0.9,
        graph_depth=entity_id - 1,
        relation_reason=(
            "direct hybrid-search hit"
            if entity_id == 1
            else "Demo.method1 CALLS_METHOD Demo.method2"
        ),
        seed_entity_id=1,
    )


def graph() -> GraphResult:
    nodes = tuple(
        GraphNode(
            entity_id=entity_id,
            label=f"Demo.method{entity_id}",
            entity_type="java_method",
            qualified_name=f"Demo.method{entity_id}",
            file_path=f"src/Demo{entity_id}.java",
            start_line=entity_id,
            end_line=entity_id + 1,
            content=f"method {entity_id}",
            metadata={},
        )
        for entity_id in (1, 2)
    )
    return GraphResult(
        nodes=nodes,
        edges=(
            GraphEdge(
                relation_id=7,
                source_id=1,
                target_id=2,
                relation_type="CALLS_METHOD",
                confidence=0.8,
                metadata={"resolution": "receiver_type"},
            ),
        ),
    )


def test_builds_cited_context_with_separate_stored_edges() -> None:
    context = GraphContextBuilder(max_context_chars=2000).build(
        [result(1, "controller code"), result(2, "service code")],
        graph(),
    )

    assert "[1] src/Demo1.java:1-2" in context.text
    assert "[2] src/Demo2.java:2-3" in context.text
    assert "Graph depth: 1" in context.text
    assert (
        "Relation reason: Demo.method1 CALLS_METHOD Demo.method2"
        in context.text
    )
    assert "Stored graph edges (authoritative):" in context.text
    assert (
        "Demo.method1 -[CALLS_METHOD confidence=0.8]-> Demo.method2"
        in context.text
    )
    assert [reference.citation for reference in context.references] == [1, 2]
    assert context.references[1].file_path == "src/Demo2.java"


def test_budget_omits_later_nodes_and_never_exceeds_limit() -> None:
    builder = GraphContextBuilder(max_context_chars=420)

    context = builder.build(
        [
            result(1, "a" * 80),
            result(2, "b" * 1000),
        ],
        graph(),
    )

    assert len(context.text) <= 420
    assert [reference.entity_id for reference in context.references] == [1]
    assert "b" * 100 not in context.text


def test_empty_results_produce_empty_context() -> None:
    context = GraphContextBuilder().build([], GraphResult())

    assert context.text == ""
    assert context.references == ()
