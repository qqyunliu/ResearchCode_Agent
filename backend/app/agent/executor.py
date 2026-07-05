from typing import Any, Protocol

from app.agent.types import AgentResult, TaskType
from app.errors import DomainError
from app.schemas.agent import CodeQaResponse, TraceResponse


class CodeQaTaskService(Protocol):
    def answer(
        self,
        project_id: int,
        question: str,
        limit: int,
    ) -> CodeQaResponse: ...


class TraceTaskService(Protocol):
    def answer(
        self,
        project_id: int,
        question: str,
        *,
        limit: int,
        max_depth: int,
    ) -> TraceResponse: ...


class ChangePlanTaskService(Protocol):
    def answer(
        self,
        project_id: int,
        question: str,
        limit: int,
    ) -> object: ...


class AgentExecutor:
    def __init__(
        self,
        *,
        code_qa: CodeQaTaskService,
        trace: TraceTaskService,
        change_plan: ChangePlanTaskService,
    ) -> None:
        self.code_qa = code_qa
        self.trace = trace
        self.change_plan = change_plan

    def execute(
        self,
        task_type: TaskType | str,
        *,
        project_id: int,
        question: str,
        limit: int,
    ) -> AgentResult:
        if task_type == TaskType.CODE_QA:
            response = self.code_qa.answer(
                project_id=project_id,
                question=question,
                limit=limit,
            )
        elif task_type == TaskType.TRACE_CHAIN:
            response = self.trace.answer(
                project_id=project_id,
                question=question,
                limit=limit,
                max_depth=2,
            )
        elif task_type == TaskType.CHANGE_PLAN:
            response = self.change_plan.answer(
                project_id=project_id,
                question=question,
                limit=limit,
            )
        else:
            raise DomainError(
                code="AGENT_TASK_UNSUPPORTED",
                message=f"Agent task '{task_type}' is not supported.",
                status_code=500,
            )
        return self._normalize(TaskType(task_type), response)

    @staticmethod
    def _normalize(
        task_type: TaskType,
        response: Any,
    ) -> AgentResult:
        return AgentResult(
            task_type=task_type,
            answer=response.answer,
            references=tuple(getattr(response, "references", ())),
            graph_nodes=tuple(getattr(response, "graph_nodes", ())),
            graph_edges=tuple(getattr(response, "graph_edges", ())),
            uncertainties=tuple(
                getattr(response, "uncertainties", ())
            ),
        )
