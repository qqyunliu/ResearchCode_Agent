import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.types import AgentResult
from app.errors import DomainError
from app.models import Conversation, Message, Project
from app.models.base import utc_now


class ConversationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, project_id: int, title: str) -> Conversation:
        self._require_project(project_id)
        conversation = Conversation(
            project_id=project_id,
            title=title.strip(),
        )
        self.session.add(conversation)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(conversation)
        return conversation

    def get_for_project(
        self,
        conversation_id: int,
        project_id: int,
    ) -> Conversation:
        conversation = self.session.get(
            Conversation,
            conversation_id,
        )
        if conversation is None:
            raise DomainError(
                code="CONVERSATION_NOT_FOUND",
                message=(
                    f"Conversation {conversation_id} does not exist."
                ),
                status_code=404,
            )
        if conversation.project_id != project_id:
            raise DomainError(
                code="CONVERSATION_PROJECT_MISMATCH",
                message=(
                    f"Conversation {conversation_id} does not belong "
                    f"to project {project_id}."
                ),
                status_code=409,
            )
        return conversation

    def validate_target(
        self,
        project_id: int,
        conversation_id: int | None,
    ) -> None:
        if conversation_id is None:
            self._require_project(project_id)
        else:
            self.get_for_project(conversation_id, project_id)

    def save_exchange(
        self,
        project_id: int,
        question: str,
        result: AgentResult,
        conversation_id: int | None,
    ) -> tuple[Conversation, Message]:
        normalized_question = question.strip()
        try:
            if conversation_id is None:
                self._require_project(project_id)
                conversation = Conversation(
                    project_id=project_id,
                    title=normalized_question[:80],
                )
                self.session.add(conversation)
            else:
                conversation = self.get_for_project(
                    conversation_id,
                    project_id,
                )

            user_message = Message(
                role="user",
                content=normalized_question,
                task_type=None,
                metadata_json="{}",
            )
            assistant_message = Message(
                role="assistant",
                content=result.answer,
                task_type=result.task_type.value,
                metadata_json=self._metadata(result),
            )
            conversation.messages.extend(
                [user_message, assistant_message]
            )
            conversation.updated_at = utc_now()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(conversation)
        self.session.refresh(assistant_message)
        return conversation, assistant_message

    def get_history(self, conversation_id: int) -> Conversation:
        conversation = self.session.get(
            Conversation,
            conversation_id,
        )
        if conversation is None:
            raise DomainError(
                code="CONVERSATION_NOT_FOUND",
                message=(
                    f"Conversation {conversation_id} does not exist."
                ),
                status_code=404,
            )
        return conversation

    def _require_project(self, project_id: int) -> Project:
        project = self.session.scalar(
            select(Project).where(Project.id == project_id)
        )
        if project is None:
            raise DomainError(
                code="PROJECT_NOT_FOUND",
                message=f"Project {project_id} does not exist.",
                status_code=404,
            )
        return project

    @staticmethod
    def _metadata(result: AgentResult) -> str:
        value = {
            "references": [
                reference.model_dump(mode="json")
                for reference in result.references
            ],
            "graph_nodes": [
                node.model_dump(mode="json")
                for node in result.graph_nodes
            ],
            "graph_edges": [
                edge.model_dump(mode="json")
                for edge in result.graph_edges
            ],
            "uncertainties": list(result.uncertainties),
        }
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )
