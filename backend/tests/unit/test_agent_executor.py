from typing import Any

import pytest

from app.agent.executor import AgentExecutor
from app.agent.types import AgentResult, TaskType
from app.errors import DomainError
from app.schemas.agent import (
    CodeQaResponse,
    ContextReferenceRead,
    TraceResponse,
)
from app.schemas.graph import GraphEdgeRead, GraphNodeRead


def reference() -> ContextReferenceRead:
    return ContextReferenceRead(
        citation=1,
        entity_id=5,
        file_path="backend/src/AlertController.java",
        start_line=4,
        end_line=7,
        entity_type="java_method",
        qualified_name="AlertController.getAlert",
    )


def graph_node() -> GraphNodeRead:
    return GraphNodeRead(
        entity_id=5,
        label="AlertController.getAlert",
        entity_type="java_method",
        qualified_name="AlertController.getAlert",
        file_path="backend/src/AlertController.java",
        start_line=4,
        end_line=7,
        content="return alertService.findById(id);",
        metadata={},
    )


def graph_edge() -> GraphEdgeRead:
    return GraphEdgeRead(
        relation_id=9,
        source_id=5,
        target_id=10,
        relation_type="CALLS_METHOD",
        confidence=0.8,
        metadata={},
    )


class FakeService:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def answer(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return self.response


def make_executor() -> tuple[
    AgentExecutor,
    FakeService,
    FakeService,
    FakeService,
]:
    code_qa = FakeService(
        CodeQaResponse(
            answer="Code answer [1].",
            references=[reference()],
        )
    )
    trace = FakeService(
        TraceResponse(
            answer="Trace answer [1].",
            references=[reference()],
            graph_nodes=[graph_node()],
            graph_edges=[graph_edge()],
            uncertainties=["Service implementation is incomplete."],
        )
    )
    change_plan = FakeService(
        TraceResponse(
            answer="Change backend/src/AlertController.java [1].",
            references=[reference()],
            graph_nodes=[graph_node()],
            graph_edges=[],
            uncertainties=["DTO location requires confirmation."],
        )
    )
    return (
        AgentExecutor(
            code_qa=code_qa,
            trace=trace,
            change_plan=change_plan,
        ),
        code_qa,
        trace,
        change_plan,
    )


def test_executor_routes_code_qa_and_normalizes_result() -> None:
    executor, code_qa, trace, change_plan = make_executor()

    result = executor.execute(
        TaskType.CODE_QA,
        project_id=1,
        question="Where is getAlert?",
        limit=5,
    )

    assert result == AgentResult(
        task_type=TaskType.CODE_QA,
        answer="Code answer [1].",
        references=(reference(),),
    )
    assert code_qa.calls == [
        {
            "project_id": 1,
            "question": "Where is getAlert?",
            "limit": 5,
        }
    ]
    assert trace.calls == []
    assert change_plan.calls == []


def test_executor_routes_trace_with_two_hop_limit() -> None:
    executor, code_qa, trace, change_plan = make_executor()

    result = executor.execute(
        TaskType.TRACE_CHAIN,
        project_id=2,
        question="Trace the alert data",
        limit=7,
    )

    assert result.task_type is TaskType.TRACE_CHAIN
    assert result.graph_nodes == (graph_node(),)
    assert result.graph_edges == (graph_edge(),)
    assert result.uncertainties == (
        "Service implementation is incomplete.",
    )
    assert trace.calls == [
        {
            "project_id": 2,
            "question": "Trace the alert data",
            "limit": 7,
            "max_depth": 2,
        }
    ]
    assert code_qa.calls == []
    assert change_plan.calls == []


def test_executor_routes_change_plan() -> None:
    executor, code_qa, trace, change_plan = make_executor()

    result = executor.execute(
        TaskType.CHANGE_PLAN,
        project_id=3,
        question="Add risk_score",
        limit=4,
    )

    assert result.task_type is TaskType.CHANGE_PLAN
    assert result.references == (reference(),)
    assert result.graph_nodes == (graph_node(),)
    assert result.graph_edges == ()
    assert result.uncertainties == (
        "DTO location requires confirmation.",
    )
    assert change_plan.calls == [
        {
            "project_id": 3,
            "question": "Add risk_score",
            "limit": 4,
        }
    ]
    assert code_qa.calls == []
    assert trace.calls == []


def test_executor_rejects_unsupported_task() -> None:
    executor, code_qa, trace, change_plan = make_executor()

    with pytest.raises(DomainError) as raised:
        executor.execute(
            "UNKNOWN",
            project_id=1,
            question="question",
            limit=5,
        )

    assert raised.value.code == "AGENT_TASK_UNSUPPORTED"
    assert raised.value.message == "Agent task 'UNKNOWN' is not supported."
    assert raised.value.status_code == 500
    assert code_qa.calls == []
    assert trace.calls == []
    assert change_plan.calls == []
