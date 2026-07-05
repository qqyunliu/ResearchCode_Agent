from pydantic import BaseModel, ConfigDict, Field

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
