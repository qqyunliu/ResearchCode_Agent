from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.types import AgentResult, TaskType
from app.api.agent_api import (
    get_agent_chat_service,
    get_conversation_service,
)
from app.main import app
from app.models import Base, Project
from app.schemas.agent import AgentChatResponse
from app.services.agent_chat_service import AgentChatService
from app.services.conversation_service import ConversationService


class FakeAgentChatService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int | None, int]] = []

    def answer(
        self,
        *,
        project_id: int,
        question: str,
        conversation_id: int | None,
        limit: int,
    ) -> AgentChatResponse:
        self.calls.append(
            (project_id, question, conversation_id, limit)
        )
        return AgentChatResponse(
            conversation_id=12,
            message_id=24,
            task_type=TaskType.CODE_QA,
            answer="Answer",
            references=[],
            graph_nodes=[],
            graph_edges=[],
            uncertainties=[],
        )


class FixedPlanner:
    def plan(self, question: str) -> TaskType:
        return TaskType.CODE_QA


class EchoExecutor:
    def execute(
        self,
        task_type: TaskType,
        *,
        project_id: int,
        question: str,
        limit: int,
    ) -> AgentResult:
        return AgentResult(
            task_type=task_type,
            answer=f"Answer to: {question}",
        )


def test_chat_endpoint_uses_overridable_service(client) -> None:
    service = FakeAgentChatService()
    app.dependency_overrides[get_agent_chat_service] = lambda: service

    response = client.post(
        "/api/agent/chat",
        json={
            "project_id": 3,
            "question": "Where is the API?",
            "conversation_id": 8,
            "limit": 7,
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == 12
    assert response.json()["message_id"] == 24
    assert service.calls == [(3, "Where is the API?", 8, 7)]


def test_chat_endpoint_rejects_blank_question_and_invalid_limit(client) -> None:
    service = FakeAgentChatService()
    app.dependency_overrides[get_agent_chat_service] = lambda: service

    blank = client.post(
        "/api/agent/chat",
        json={"project_id": 1, "question": "   "},
    )
    invalid_limit = client.post(
        "/api/agent/chat",
        json={"project_id": 1, "question": "Question", "limit": 21},
    )

    assert blank.status_code == 422
    assert invalid_limit.status_code == 422
    assert service.calls == []


def test_new_and_continued_chat_can_be_reloaded_chronologically(
    client,
    tmp_path,
) -> None:
    database_path = tmp_path / "agent-chat.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(name="Demo", root_path=str(tmp_path / "demo"))
        session.add(project)
        session.commit()
        service = AgentChatService(
            planner=FixedPlanner(),
            executor=EchoExecutor(),
            conversations=ConversationService(session),
        )
        app.dependency_overrides[get_agent_chat_service] = lambda: service
        app.dependency_overrides[get_conversation_service] = (
            lambda: ConversationService(session)
        )

        first = client.post(
            "/api/agent/chat",
            json={"project_id": project.id, "question": "First"},
        )
        conversation_id = first.json()["conversation_id"]
        second = client.post(
            "/api/agent/chat",
            json={
                "project_id": project.id,
                "question": "Second",
                "conversation_id": conversation_id,
            },
        )
        loaded = client.get(
            f"/api/agent/conversations/{conversation_id}",
            params={"project_id": project.id},
        )

    engine.dispose()
    assert first.status_code == 200
    assert second.status_code == 200
    assert loaded.status_code == 200
    assert [message["content"] for message in loaded.json()["messages"]] == [
        "First",
        "Answer to: First",
        "Second",
        "Answer to: Second",
    ]
    assert loaded.json()["messages"][1]["task_type"] == "CODE_QA"


def test_conversation_read_maps_not_found_and_project_mismatch(
    client,
    tmp_path,
) -> None:
    database_path = tmp_path / "agent-chat-errors.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        first_project = Project(
            name="First",
            root_path=str(tmp_path / "first"),
        )
        second_project = Project(
            name="Second",
            root_path=str(tmp_path / "second"),
        )
        session.add_all([first_project, second_project])
        session.commit()
        conversations = ConversationService(session)
        conversation, _ = conversations.save_exchange(
            first_project.id,
            "Question",
            AgentResult(
                task_type=TaskType.CODE_QA,
                answer="Answer",
            ),
            None,
        )
        service = AgentChatService(
            planner=FixedPlanner(),
            executor=EchoExecutor(),
            conversations=conversations,
        )
        app.dependency_overrides[get_agent_chat_service] = lambda: service
        app.dependency_overrides[get_conversation_service] = (
            lambda: conversations
        )

        missing = client.get(
            "/api/agent/conversations/999",
            params={"project_id": first_project.id},
        )
        mismatch = client.get(
            f"/api/agent/conversations/{conversation.id}",
            params={"project_id": second_project.id},
        )

    engine.dispose()
    assert missing.status_code == 404
    assert mismatch.status_code == 409
