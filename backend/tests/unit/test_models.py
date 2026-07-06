import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Conversation, Message, Project


def test_metadata_contains_all_application_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "projects",
        "code_files",
        "code_entities",
        "code_relations",
        "conversations",
        "messages",
        "scan_issues",
    }
    assert "sort_order" in {
        column["name"] for column in inspect(engine).get_columns("projects")
    }


def test_conversation_orders_messages_and_project_delete_cascades() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(name="Demo", root_path="F:/demo")
        session.add(project)
        session.flush()
        conversation = Conversation(
            project_id=project.id,
            title="Alert flow",
        )
        session.add(conversation)
        session.flush()
        session.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content="Where is the alert API?",
                    task_type=None,
                    metadata_json="{}",
                ),
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content="It is in AlertController.",
                    task_type="CODE_QA",
                    metadata_json='{"references":[]}',
                ),
            ]
        )
        session.commit()

        assert [message.role for message in conversation.messages] == [
            "user",
            "assistant",
        ]

        session.delete(project)
        session.commit()

        assert session.scalar(
            select(func.count()).select_from(Conversation)
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(Message)
        ) == 0
    engine.dispose()


def test_message_role_constraint_rejects_unknown_role() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(name="Demo", root_path="F:/demo")
        session.add(project)
        session.flush()
        conversation = Conversation(
            project_id=project.id,
            title="Alert flow",
        )
        session.add(conversation)
        session.flush()
        session.add(
            Message(
                conversation_id=conversation.id,
                role="system",
                content="Not allowed",
                metadata_json="{}",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()
