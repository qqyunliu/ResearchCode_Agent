import json
import shutil
from pathlib import Path

from qdrant_client import QdrantClient

from app.core.dependencies import (
    get_embedding_service,
    get_llm_client,
    get_vector_store,
)
from app.errors import DomainError
from app.main import app
from app.retrieval.vector_store import QdrantVectorStore


class DeterministicEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if "alertcontroller" in normalized or "api/alerts" in normalized:
            return [1.0, 0.0, 0.0]
        if "alertservice" in normalized or "findbyid" in normalized:
            return [0.8, 0.2, 0.0]
        if "alert" in normalized or "risk_score" in normalized:
            return [0.7, 0.3, 0.0]
        return [0.0, 0.0, 1.0]


class RecordingFakeLlm:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_next = False

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.fail_next:
            self.fail_next = False
            raise DomainError(
                code="LLM_REQUEST_FAILED",
                message="Injected offline LLM failure.",
                status_code=502,
            )
        if "Return one JSON object" in system_prompt:
            return json.dumps({
                "summary": "Add risk_score only in supported indexed code.",
                "affected_files": [],
                "risks": ["Schema compatibility requires review."],
                "uncertainties": [
                    "No grounded affected file was selected by the fake LLM."
                ],
            })
        return "The indexed alert flow is supported by the cited code [1]."


def create_scanned_project(client, tmp_path, name: str) -> int:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / name
    shutil.copytree(source, project_root)
    created = client.post(
        "/api/projects",
        json={"name": name, "root_path": str(project_root)},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert client.post(f"/api/projects/{project_id}/scan").status_code == 200
    return project_id


def test_week4_unified_agent_offline_acceptance(client, tmp_path) -> None:
    llm = RecordingFakeLlm()
    vector_store = QdrantVectorStore(QdrantClient(":memory:"))
    app.dependency_overrides[get_embedding_service] = (
        lambda: DeterministicEmbeddings()
    )
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_llm_client] = lambda: llm

    project_id = create_scanned_project(client, tmp_path, "week4-primary")
    other_id = create_scanned_project(client, tmp_path, "week4-other")
    build = client.post(
        f"/api/projects/{project_id}/build-vector-index"
    )
    assert build.status_code == 200
    assert build.json()["chunks_indexed"] == 13

    questions = [
        "Where is the alert API implemented?",
        "Trace the alert request chain.",
        "Add risk_score; which files need changes?",
    ]
    expected_types = ["CODE_QA", "TRACE_CHAIN", "CHANGE_PLAN"]
    conversation_id = None
    responses = []
    for question, expected_type in zip(questions, expected_types):
        payload = {
            "project_id": project_id,
            "question": question,
            "limit": 5,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        response = client.post("/api/agent/chat", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["task_type"] == expected_type
        assert data["references"]
        if expected_type == "TRACE_CHAIN":
            assert data["graph_nodes"]
        if expected_type == "CHANGE_PLAN":
            assert data["uncertainties"]
        conversation_id = data["conversation_id"]
        responses.append(data)

    history = client.get(
        f"/api/agent/conversations/{conversation_id}",
        params={"project_id": project_id},
    )
    assert history.status_code == 200
    assert [message["role"] for message in history.json()["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert client.get(
        f"/api/agent/conversations/{conversation_id}",
        params={"project_id": other_id},
    ).status_code == 409

    assert questions[0] in llm.calls[0][1]
    assert questions[0] in llm.calls[1][1]
    assert questions[1] in llm.calls[2][1]
    assert "Conversation context (not code evidence):" in llm.calls[1][1]

    llm.fail_next = True
    failed = client.post(
        "/api/agent/chat",
        json={
            "project_id": project_id,
            "question": "Where is AlertController?",
            "conversation_id": conversation_id,
            "limit": 5,
        },
    )
    assert failed.status_code == 502
    unchanged = client.get(
        f"/api/agent/conversations/{conversation_id}",
        params={"project_id": project_id},
    )
    assert len(unchanged.json()["messages"]) == 6
