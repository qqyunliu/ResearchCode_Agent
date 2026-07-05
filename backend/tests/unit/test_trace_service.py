from dataclasses import replace

import pytest

from app.errors import DomainError
from app.graph.types import GraphEdge, GraphNode, GraphResult
from app.rag.graph_context_builder import GraphContextBuilder
from app.rag.graph_retriever import GraphRetrievalResult
from app.services.trace_service import (
    NO_TRACE_EVIDENCE_ANSWER,
    TraceService,
)


def retrieval_result() -> GraphRetrievalResult:
    return GraphRetrievalResult(
        entity_id=5,
        entity_type="java_method",
        name="getAlert",
        qualified_name="AlertController.getAlert",
        file_path="backend/src/AlertController.java",
        start_line=10,
        end_line=13,
        content="return alertService.findById(id);",
        metadata={},
        retrieval_score=0.9,
        graph_depth=0,
        relation_reason="direct hybrid-search hit",
        seed_entity_id=5,
    )


def trace_graph() -> GraphResult:
    return GraphResult(
        nodes=(
            GraphNode(
                entity_id=5,
                label="AlertController.getAlert",
                entity_type="java_method",
                qualified_name="AlertController.getAlert",
                file_path="backend/src/AlertController.java",
                start_line=10,
                end_line=13,
                content="return alertService.findById(id);",
                metadata={},
            ),
            GraphNode(
                entity_id=10,
                label="AlertService.findById",
                entity_type="java_method",
                qualified_name="AlertService.findById",
                file_path="backend/src/AlertService.java",
                start_line=3,
                end_line=5,
                content="return null;",
                metadata={},
            ),
        ),
        edges=(
            GraphEdge(
                relation_id=10,
                source_id=5,
                target_id=10,
                relation_type="CALLS_METHOD",
                confidence=0.8,
                metadata={},
            ),
        ),
    )


class FakeRetriever:
    def __init__(self, results: list[GraphRetrievalResult]) -> None:
        self.results = results
        self.calls: list[tuple[int, str, int, int]] = []

    def retrieve(
        self,
        project_id: int,
        query: str,
        *,
        limit: int,
        max_depth: int,
    ) -> list[GraphRetrievalResult]:
        self.calls.append((project_id, query, limit, max_depth))
        return self.results


class FakeGraph:
    def __init__(self, result: GraphResult) -> None:
        self.result = result
        self.calls: list[tuple[int, tuple[int, ...], int]] = []

    def expand_entities(
        self,
        project_id: int,
        entity_ids,
        *,
        max_depth: int,
    ) -> GraphResult:
        self.calls.append(
            (project_id, tuple(entity_ids), max_depth)
        )
        return self.result


class FakeLlm:
    def __init__(self, answer: str = "Controller calls service [1].") -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.answer


def test_trace_uses_grounded_graph_context_and_returns_graph() -> None:
    controller_result = retrieval_result()
    service_result = replace(
        controller_result,
        entity_id=10,
        name="findById",
        qualified_name="AlertService.findById",
        file_path="backend/src/AlertService.java",
        start_line=3,
        end_line=5,
        content="return null;",
        graph_depth=1,
        relation_reason=(
            "AlertController.getAlert CALLS_METHOD "
            "AlertService.findById"
        ),
    )
    retriever = FakeRetriever([controller_result, service_result])
    graph = FakeGraph(trace_graph())
    llm = FakeLlm()
    service = TraceService(
        retriever=retriever,
        graph=graph,
        context_builder=GraphContextBuilder(),
        llm=llm,
    )

    response = service.answer(
        1,
        "Trace the alert request",
        limit=5,
        max_depth=2,
    )

    assert retriever.calls == [(1, "Trace the alert request", 5, 2)]
    assert graph.calls == [(1, (5,), 2)]
    assert len(llm.calls) == 1
    system_prompt, user_prompt = llm.calls[0]
    assert "stored CALLS_METHOD edge" in system_prompt
    assert "cannot be determined from indexed code" in system_prompt
    assert "chain, involved files, and uncertain" in system_prompt
    assert "Stored graph edges (authoritative):" in user_prompt
    assert "Question:\nTrace the alert request" in user_prompt
    assert response.answer == "Controller calls service [1]."
    assert response.references[0].entity_id == 5
    assert response.graph_nodes[1].entity_id == 10
    assert response.graph_edges[0].relation_type == "CALLS_METHOD"
    assert any(
        "REQUESTS_API" in uncertainty
        for uncertainty in response.uncertainties
    )


def test_no_results_skip_graph_and_llm() -> None:
    retriever = FakeRetriever([])
    graph = FakeGraph(GraphResult())
    llm = FakeLlm()
    service = TraceService(
        retriever=retriever,
        graph=graph,
        context_builder=GraphContextBuilder(),
        llm=llm,
    )

    response = service.answer(
        1,
        "missing",
        limit=5,
        max_depth=2,
    )

    assert response.answer == NO_TRACE_EVIDENCE_ANSWER
    assert response.references == []
    assert response.graph_nodes == []
    assert response.graph_edges == []
    assert response.uncertainties
    assert graph.calls == []
    assert llm.calls == []


def test_llm_failure_becomes_domain_error() -> None:
    class FailingLlm:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("provider unavailable")

    service = TraceService(
        retriever=FakeRetriever([retrieval_result()]),
        graph=FakeGraph(trace_graph()),
        context_builder=GraphContextBuilder(),
        llm=FailingLlm(),
    )

    with pytest.raises(DomainError) as error:
        service.answer(1, "trace", limit=5, max_depth=2)

    assert error.value.code == "LLM_REQUEST_FAILED"
    assert error.value.status_code == 502
