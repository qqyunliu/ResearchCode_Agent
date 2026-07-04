from pydantic import BaseModel, ConfigDict, Field


class VectorIndexSummary(BaseModel):
    project_id: int
    collection_name: str
    chunks_indexed: int


class SearchRequest(BaseModel):
    project_id: int
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)

    model_config = ConfigDict(str_strip_whitespace=True)


class SearchHitRead(BaseModel):
    entity_id: int
    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]
    score: float
    source: str
