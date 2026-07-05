from pydantic import BaseModel, ConfigDict, Field

from app.graph.types import GraphResult


class GraphNodeRead(BaseModel):
    entity_id: int
    label: str
    entity_type: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]

    model_config = ConfigDict(from_attributes=True)


class GraphEdgeRead(BaseModel):
    relation_id: int
    source_id: int
    target_id: int
    relation_type: str
    confidence: float
    metadata: dict[str, object]

    model_config = ConfigDict(from_attributes=True)


class GraphReferenceRead(BaseModel):
    citation: int
    entity_id: int
    file_path: str
    start_line: int
    end_line: int
    entity_type: str
    qualified_name: str


class GraphResponse(BaseModel):
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    references: list[GraphReferenceRead]

    @classmethod
    def from_result(cls, result: GraphResult) -> "GraphResponse":
        return cls(
            nodes=[
                GraphNodeRead.model_validate(node)
                for node in result.nodes
            ],
            edges=[
                GraphEdgeRead.model_validate(edge)
                for edge in result.edges
            ],
            references=[
                GraphReferenceRead(
                    citation=index,
                    entity_id=node.entity_id,
                    file_path=node.file_path,
                    start_line=node.start_line,
                    end_line=node.end_line,
                    entity_type=node.entity_type,
                    qualified_name=node.qualified_name,
                )
                for index, node in enumerate(result.nodes, start=1)
            ],
        )


class SearchChainRequest(BaseModel):
    project_id: int
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)
    max_depth: int = Field(default=2, ge=1, le=2)

    model_config = ConfigDict(str_strip_whitespace=True)
