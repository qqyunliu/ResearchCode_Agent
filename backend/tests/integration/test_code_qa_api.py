from app.api.agent_api import get_code_qa_service
from app.main import app
from app.schemas.agent import CodeQaResponse, ContextReferenceRead


class FakeCodeQaService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int]] = []

    def answer(
        self,
        project_id: int,
        question: str,
        limit: int,
    ) -> CodeQaResponse:
        self.calls.append((project_id, question, limit))
        return CodeQaResponse(
            answer="The API is in AlertController [1].",
            references=[
                ContextReferenceRead(
                    citation=1,
                    entity_id=5,
                    file_path="backend/src/AlertController.java",
                    start_line=4,
                    end_line=7,
                    entity_type="java_method",
                    qualified_name="AlertController.getAlert",
                )
            ],
        )


def test_code_qa_endpoint_uses_overridable_service(client) -> None:
    service = FakeCodeQaService()
    app.dependency_overrides[get_code_qa_service] = lambda: service

    response = client.post(
        "/api/agent/code-qa",
        json={
            "project_id": 1,
            "question": "Where is the alert API implemented?",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "The API is in AlertController [1]."
    )
    assert response.json()["references"][0]["citation"] == 1
    assert service.calls == [
        (1, "Where is the alert API implemented?", 5)
    ]


def test_code_qa_endpoint_rejects_blank_question(client) -> None:
    service = FakeCodeQaService()
    app.dependency_overrides[get_code_qa_service] = lambda: service

    response = client.post(
        "/api/agent/code-qa",
        json={
            "project_id": 1,
            "question": "   ",
            "limit": 5,
        },
    )

    assert response.status_code == 422
    assert service.calls == []
