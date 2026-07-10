from typing import Protocol

from app.agent.tool_registry import ToolRegistry
from app.agent.types import AgentResult, TaskType
from app.schemas.agent import AgentChatResponse


class AgentPlanner(Protocol):
    def plan(self, question: str) -> TaskType: ...


class AgentTaskExecutor(Protocol):
    def execute(
        self,
        task_type: TaskType,
        *,
        project_id: int,
        question: str,
        limit: int,
    ) -> AgentResult: ...


class AgentConversations(Protocol):
    def validate_target(
        self,
        project_id: int,
        conversation_id: int | None,
    ) -> None: ...

    def save_exchange(
        self,
        project_id: int,
        question: str,
        result: AgentResult,
        conversation_id: int | None,
    ): ...

    def get_working_memory(
        self,
        project_id: int,
        conversation_id: int | None,
    ) -> str: ...

class AgentChatService:
    def __init__(
        self,
        *,
        planner: AgentPlanner,
        executor: AgentTaskExecutor,
        conversations: AgentConversations,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.conversations = conversations
        self.tools = tools or ToolRegistry()

    @property
    def tool_names(self) -> tuple[str, ...]:
        return self.tools.names

    def answer(
        self,
        *,
        project_id: int,
        question: str,
        conversation_id: int | None,
        limit: int,
    ) -> AgentChatResponse:
        self.conversations.validate_target(
            project_id,
            conversation_id,
        )
        conversation_memory = self.conversations.get_working_memory(
            project_id,
            conversation_id,
        )
        task_type = self.planner.plan(question)
        result = self.executor.execute(
            task_type,
            project_id=project_id,
            question=question,
            limit=limit,
            conversation_memory=conversation_memory,
        )
        conversation, assistant_message = (
            self.conversations.save_exchange(
                project_id,
                question,
                result,
                conversation_id,
            )
        )
        return AgentChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            task_type=result.task_type,
            answer=result.answer,
            references=list(result.references),
            graph_nodes=list(result.graph_nodes),
            graph_edges=list(result.graph_edges),
            uncertainties=list(result.uncertainties),
        )
