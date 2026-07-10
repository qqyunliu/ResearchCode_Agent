from types import SimpleNamespace

import pytest

from app.agent.tool_registry import ToolRegistry
from app.agent.types import AgentResult, TaskType
from app.schemas.agent import ContextReferenceRead
from app.services.agent_chat_service import AgentChatService


def result() -> AgentResult:
    return AgentResult(
        task_type=TaskType.CODE_QA,
        answer="The API is implemented in AlertController [1].",
        references=(
            ContextReferenceRead(
                citation=1,
                entity_id=5,
                file_path="backend/src/AlertController.java",
                start_line=10,
                end_line=13,
                entity_type="java_method",
                qualified_name="AlertController.getAlert",
            ),
        ),
        uncertainties=("Service behavior requires confirmation.",),
    )


class RecordingPlanner:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def plan(self, question: str) -> TaskType:
        self.questions.append(question)
        return TaskType.CODE_QA


class RecordingExecutor:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[tuple[TaskType, int, str, int, str]] = []
        self.failure = failure

    def execute(
        self,
        task_type: TaskType,
        *,
        project_id: int,
        question: str,
        limit: int,
        conversation_memory: str,
    ) -> AgentResult:
        self.calls.append(
            (task_type, project_id, question, limit, conversation_memory)
        )
        if self.failure is not None:
            raise self.failure
        return result()


class RecordingConversations:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.saved: list[tuple] = []

    def validate_target(
        self,
        project_id: int,
        conversation_id: int | None,
    ) -> None:
        self.events.append(("validate", project_id, conversation_id))

    def save_exchange(
        self,
        project_id: int,
        question: str,
        agent_result: AgentResult,
        conversation_id: int | None,
    ):
        self.events.append(("save",))
        self.saved.append(
            (project_id, question, agent_result, conversation_id)
        )
        return (
            SimpleNamespace(id=17),
            SimpleNamespace(id=29),
        )

    def get_history(self, conversation_id: int):
        self.events.append(("history", conversation_id))
        raise AssertionError("history must not be read while answering")

    def get_working_memory(
        self,
        project_id: int,
        conversation_id: int | None,
    ) -> str:
        self.events.append(("memory", project_id, conversation_id))
        if conversation_id is None:
            return ""
        return "Conversation context (not code evidence):\nUser: Alert API"


def make_service(
    *,
    executor: RecordingExecutor | None = None,
    conversations: RecordingConversations | None = None,
):
    planner = RecordingPlanner()
    executor = executor or RecordingExecutor()
    conversations = conversations or RecordingConversations()
    service = AgentChatService(
        planner=planner,
        executor=executor,
        conversations=conversations,
        tools=ToolRegistry(),
    )
    return service, planner, executor, conversations


def test_answer_routes_only_current_question_and_persists_result() -> None:
    service, planner, executor, conversations = make_service()

    response = service.answer(
        project_id=3,
        question="Where is the alert API?",
        conversation_id=8,
        limit=7,
    )

    assert planner.questions == ["Where is the alert API?"]
    assert executor.calls == [
        (TaskType.CODE_QA, 3, "Where is the alert API?", 7, "Conversation context (not code evidence):\nUser: Alert API")
    ]
    assert conversations.events == [
        ("validate", 3, 8),
        ("memory", 3, 8),
        ("save",),
    ]
    assert conversations.saved == [
        (3, "Where is the alert API?", result(), 8)
    ]
    assert response.conversation_id == 17
    assert response.message_id == 29
    assert response.task_type is TaskType.CODE_QA
    assert response.references[0].entity_id == 5


def test_chinese_question_is_preserved_for_planning_execution_and_storage() -> None:
    service, planner, executor, conversations = make_service()
    question = "告警列表 API 在哪里实现？"

    service.answer(
        project_id=3,
        question=question,
        conversation_id=None,
        limit=5,
    )

    assert planner.questions == [question]
    assert executor.calls == [(TaskType.CODE_QA, 3, question, 5, "")]
    assert conversations.saved[0][1] == question


def test_answer_does_not_persist_when_executor_fails() -> None:
    executor = RecordingExecutor(failure=RuntimeError("LLM unavailable"))
    service, _, _, conversations = make_service(executor=executor)

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        service.answer(
            project_id=3,
            question="Where is it?",
            conversation_id=None,
            limit=5,
        )

    assert conversations.events == [
        ("validate", 3, None),
        ("memory", 3, None),
    ]
    assert conversations.saved == []


def test_answer_validates_supplied_conversation_before_planning() -> None:
    conversations = RecordingConversations()

    def reject_target(project_id: int, conversation_id: int | None) -> None:
        conversations.events.append(
            ("validate", project_id, conversation_id)
        )
        raise RuntimeError("foreign conversation")

    conversations.validate_target = reject_target  # type: ignore[method-assign]
    service, planner, executor, _ = make_service(
        conversations=conversations
    )

    with pytest.raises(RuntimeError, match="foreign conversation"):
        service.answer(
            project_id=3,
            question="Where is it?",
            conversation_id=99,
            limit=5,
        )

    assert planner.questions == []
    assert executor.calls == []
    assert conversations.saved == []


def test_service_exposes_the_four_registered_agent_tools() -> None:
    tools = ToolRegistry()
    for name in (
        "hybrid_search",
        "graph_search",
        "read_entity",
        "get_related_entities",
    ):
        tools.register(name, lambda: None)

    service = AgentChatService(
        planner=RecordingPlanner(),
        executor=RecordingExecutor(),
        conversations=RecordingConversations(),
        tools=tools,
    )

    assert service.tool_names == (
        "hybrid_search",
        "graph_search",
        "read_entity",
        "get_related_entities",
    )
