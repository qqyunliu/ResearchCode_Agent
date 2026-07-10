from pydantic import BaseModel


class FrontendRequestExample(BaseModel):
    entity_id: int
    file_path: str
    start_line: int
    end_line: int
    http_method: str
    path: str
    resolution: str


class FrontendRequestWarningExample(BaseModel):
    file_path: str
    reason: str
    message: str


class FrontendRequestDiagnostics(BaseModel):
    project_id: int
    identified_calls: int
    matched_calls: int
    unmatched_calls: int
    unresolved_candidates: int
    unmatched_examples: list[FrontendRequestExample]
    unresolved_examples: list[FrontendRequestWarningExample]
