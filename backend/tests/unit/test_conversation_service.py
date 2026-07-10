import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.agent.types import AgentResult, TaskType
from app.errors import DomainError
from app.models import Base, Conversation, Message, Project
from app.schemas.agent import ContextReferenceRead
from app.services.conversation_service import ConversationService


@pytest.fixture
def conversation_session(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'conversation.db').as_posix()}"
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(
            name="Demo",
            root_path=str(tmp_path / "demo"),
        )
        other = Project(
            name="Other",
            root_path=str(tmp_path / "other"),
        )
        session.add_all([project, other])
        session.commit()
        yield session, project, other
    engine.dispose()


def agent_result() -> AgentResult:
    return AgentResult(
        task_type=TaskType.CODE_QA,
        answer="The API is in AlertController [1].",
        references=(
            ContextReferenceRead(
                citation=1,
                entity_id=5,
                file_path="backend/src/AlertController.java",
                start_line=4,
                end_line=7,
                entity_type="java_method",
                qualified_name="AlertController.getAlert",
            ),
        ),
        uncertainties=("Service behavior requires confirmation.",),
    )


def test_create_and_get_conversation_for_project(
    conversation_session,
) -> None:
    session, project, _ = conversation_session
    service = ConversationService(session)

    created = service.create(project.id, "Alert flow")
    loaded = service.get_for_project(created.id, project.id)

    assert loaded.id == created.id
    assert loaded.title == "Alert flow"
    assert loaded.messages == []


def test_create_rejects_missing_project(conversation_session) -> None:
    session, _, _ = conversation_session

    with pytest.raises(DomainError) as raised:
        ConversationService(session).create(999, "Missing")

    assert raised.value.code == "PROJECT_NOT_FOUND"
    assert raised.value.status_code == 404


def test_get_rejects_missing_or_foreign_conversation(
    conversation_session,
) -> None:
    session, project, other = conversation_session
    service = ConversationService(session)
    conversation = service.create(project.id, "Alert flow")

    with pytest.raises(DomainError) as missing:
        service.get_for_project(999, project.id)
    with pytest.raises(DomainError) as mismatch:
        service.get_for_project(conversation.id, other.id)

    assert missing.value.code == "CONVERSATION_NOT_FOUND"
    assert missing.value.status_code == 404
    assert mismatch.value.code == "CONVERSATION_PROJECT_MISMATCH"
    assert mismatch.value.status_code == 409


def test_save_exchange_creates_conversation_and_two_messages_atomically(
    conversation_session,
) -> None:
    session, project, _ = conversation_session
    service = ConversationService(session)
    question = "  Where is the alert API implemented?  "

    conversation, assistant = service.save_exchange(
        project_id=project.id,
        question=question,
        result=agent_result(),
        conversation_id=None,
    )

    assert conversation.title == "Where is the alert API implemented?"
    assert [message.role for message in conversation.messages] == [
        "user",
        "assistant",
    ]
    assert conversation.messages[0].content == (
        "Where is the alert API implemented?"
    )
    assert assistant.id == conversation.messages[1].id
    assert assistant.task_type == "CODE_QA"
    metadata = json.loads(assistant.metadata_json)
    assert metadata["references"][0]["entity_id"] == 5
    assert metadata["graph_nodes"] == []
    assert metadata["graph_edges"] == []
    assert metadata["uncertainties"] == [
        "Service behavior requires confirmation."
    ]


def test_save_exchange_continues_existing_conversation(
    conversation_session,
) -> None:
    session, project, _ = conversation_session
    service = ConversationService(session)
    conversation, _ = service.save_exchange(
        project.id,
        "First question",
        agent_result(),
        None,
    )

    continued, _ = service.save_exchange(
        project.id,
        "Second question",
        agent_result(),
        conversation.id,
    )

    assert continued.id == conversation.id
    assert [message.content for message in continued.messages] == [
        "First question",
        agent_result().answer,
        "Second question",
        agent_result().answer,
    ]


def test_title_is_limited_to_first_eighty_characters(
    conversation_session,
) -> None:
    session, project, _ = conversation_session

    conversation, _ = ConversationService(session).save_exchange(
        project.id,
        "x" * 100,
        agent_result(),
        None,
    )

    assert conversation.title == "x" * 80


def test_get_history_returns_messages_in_chronological_order(
    conversation_session,
) -> None:
    session, project, _ = conversation_session
    service = ConversationService(session)
    conversation, _ = service.save_exchange(
        project.id,
        "First",
        agent_result(),
        None,
    )
    service.save_exchange(
        project.id,
        "Second",
        agent_result(),
        conversation.id,
    )

    loaded = service.get_history(conversation.id)

    assert [message.role for message in loaded.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_get_working_memory_returns_saved_messages_for_the_project(
    conversation_session,
) -> None:
    session, project, _ = conversation_session
    service = ConversationService(session)
    conversation, _ = service.save_exchange(
        project.id,
        "Where is the alert API?",
        agent_result(),
        None,
    )

    memory = service.get_working_memory(project.id, conversation.id)

    assert "Conversation context (not code evidence):" in memory
    assert "Where is the alert API?" in memory
    assert "AlertController" in memory


def test_get_working_memory_is_empty_for_new_conversation(
    conversation_session,
) -> None:
    session, project, _ = conversation_session

    memory = ConversationService(session).get_working_memory(
        project.id,
        None,
    )

    assert memory == ""


def test_continuing_conversation_updates_its_timestamp(
    conversation_session,
) -> None:
    session, project, _ = conversation_session
    service = ConversationService(session)
    conversation, _ = service.save_exchange(
        project.id,
        "First",
        agent_result(),
        None,
    )
    conversation.updated_at = datetime(
        2000,
        1,
        1,
        tzinfo=timezone.utc,
    )
    session.commit()

    continued, _ = service.save_exchange(
        project.id,
        "Second",
        agent_result(),
        conversation.id,
    )

    assert continued.updated_at.year > 2000


def test_save_exchange_rolls_back_new_conversation_on_commit_failure(
    conversation_session,
    monkeypatch,
) -> None:
    session, project, _ = conversation_session
    real_commit = session.commit

    def fail_commit() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="database unavailable"):
        ConversationService(session).save_exchange(
            project.id,
            "Question",
            agent_result(),
            None,
        )
    monkeypatch.setattr(session, "commit", real_commit)

    assert session.scalar(
        select(func.count()).select_from(Conversation)
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(Message)
    ) == 0
