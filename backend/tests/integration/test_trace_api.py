from app.api.agent_api import get_trace_service
from app.main import app
from app.schemas.agent import (
    ContextReferenceRead,
    TraceResponse,
)
from app.schemas.graph import GraphEdgeRead, GraphNodeRead


class FakeTraceService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int, int]] = []

    def answer(
        self,
        project_id: int,
        question: str,
        *,
        limit: int,
        max_depth: int,
    ) -> TraceResponse:
        self.calls.append((project_id, question, limit, max_depth))
        return TraceResponse(
            answer="Frontend calls controller and service [1].",
            references=[
                ContextReferenceRead(
                    citation=1,
                    entity_id=5,
                    file_path="backend/src/AlertController.java",
                    start_line=10,
                    end_line=13,
                    entity_type="java_method",
                    qualified_name="AlertController.getAlert",
                )
            ],
            graph_nodes=[
                GraphNodeRead(
                    entity_id=5,
                    label="AlertController.getAlert",
                    entity_type="java_method",
                    qualified_name="AlertController.getAlert",
                    file_path="backend/src/AlertController.java",
                    start_line=10,
                    end_line=13,
                    content="return service.findById(id);",
                    metadata={},
                )
            ],
            graph_edges=[
                GraphEdgeRead(
                    relation_id=10,
                    source_id=5,
                    target_id=10,
                    relation_type="CALLS_METHOD",
                    confidence=0.8,
                    metadata={},
                )
            ],
            uncertainties=[],
        )


def test_trace_endpoint_uses_overridable_service(client) -> None:
    service = FakeTraceService()
    app.dependency_overrides[get_trace_service] = lambda: service

    response = client.post(
        "/api/agent/trace",
        json={
            "project_id": 1,
            "question": "Trace the alert request",
            "limit": 5,
            "max_depth": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["graph_edges"][0]["relation_type"] == (
        "CALLS_METHOD"
    )
    assert service.calls == [(1, "Trace the alert request", 5, 2)]


def test_trace_endpoint_rejects_blank_question_and_depth(client) -> None:
    service = FakeTraceService()
    app.dependency_overrides[get_trace_service] = lambda: service

    blank = client.post(
        "/api/agent/trace",
        json={
            "project_id": 1,
            "question": "   ",
            "max_depth": 2,
        },
    )
    too_deep = client.post(
        "/api/agent/trace",
        json={
            "project_id": 1,
            "question": "trace",
            "max_depth": 3,
        },
    )

    assert blank.status_code == 422
    assert too_deep.status_code == 422
    assert service.calls == []
