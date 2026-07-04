from pydantic import BaseModel, ConfigDict, Field


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
