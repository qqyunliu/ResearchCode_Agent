from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    root_path: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)


class ProjectRead(BaseModel):
    id: int
    name: str
    root_path: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class ProjectListItem(ProjectRead):
    created_at: datetime
    last_scan_at: datetime | None
    sort_order: int
    path_accessible: bool


class ProjectOrderUpdate(BaseModel):
    project_ids: list[int] = Field(min_length=1)


class ProjectEntityRead(BaseModel):
    entity_id: int
    entity_type: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
