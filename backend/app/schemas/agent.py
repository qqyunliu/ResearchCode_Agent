import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.agent.types import TaskType
from app.schemas.graph import GraphEdgeRead, GraphNodeRead


class CodeQaRequest(BaseModel):
    project_id: int
    question: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)

    model_config = ConfigDict(str_strip_whitespace=True)


class ContextReferenceRead(BaseModel):
    citation: int
    entity_id: int
    file_path: str
    start_line: int
    end_line: int
    entity_type: str
    qualified_name: str

    model_config = ConfigDict(from_attributes=True)


class CodeQaResponse(BaseModel):
    answer: str
    references: list[ContextReferenceRead]


class TraceRequest(BaseModel):
    project_id: int
    question: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)
    max_depth: int = Field(default=2, ge=1, le=2)

    model_config = ConfigDict(str_strip_whitespace=True)


class TraceResponse(BaseModel):
    answer: str
    references: list[ContextReferenceRead]
    graph_nodes: list[GraphNodeRead]
    graph_edges: list[GraphEdgeRead]
    uncertainties: list[str]


class AffectedFileRead(BaseModel):
    entity_id: int
    file_path: str
    reason: str
    suggested_changes: list[str]


class ChangePlanResponse(BaseModel):
    answer: str
    affected_files: list[AffectedFileRead]
    references: list[ContextReferenceRead]
    graph_nodes: list[GraphNodeRead]
    graph_edges: list[GraphEdgeRead]
    uncertainties: list[str]


class AgentChatRequest(BaseModel):
    project_id: int
    question: str = Field(min_length=1)
    conversation_id: int | None = None
    limit: int = Field(default=5, ge=1, le=20)

    model_config = ConfigDict(str_strip_whitespace=True)


class AgentChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    task_type: TaskType
    answer: str
    references: list[ContextReferenceRead]
    graph_nodes: list[GraphNodeRead]
    graph_edges: list[GraphEdgeRead]
    uncertainties: list[str]


class MessageRead(BaseModel):
    id: int
    role: str
    content: str
    task_type: TaskType | None
    references: list[ContextReferenceRead]
    graph_nodes: list[GraphNodeRead]
    graph_edges: list[GraphEdgeRead]
    uncertainties: list[str]
    created_at: datetime

    @classmethod
    def from_model(cls, message) -> "MessageRead":
        metadata = json.loads(message.metadata_json)
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            task_type=message.task_type,
            references=metadata.get("references", []),
            graph_nodes=metadata.get("graph_nodes", []),
            graph_edges=metadata.get("graph_edges", []),
            uncertainties=metadata.get("uncertainties", []),
            created_at=message.created_at,
        )


class ConversationRead(BaseModel):
    id: int
    project_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead]

    @classmethod
    def from_model(cls, conversation) -> "ConversationRead":
        return cls(
            id=conversation.id,
            project_id=conversation.project_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[
                MessageRead.from_model(message)
                for message in conversation.messages
            ],
        )
