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
