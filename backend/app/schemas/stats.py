from datetime import datetime

from pydantic import BaseModel


class ProjectStats(BaseModel):
    project_id: int
    total_files: int
    total_lines: int
    languages: dict[str, int]
    entity_types: dict[str, int]
    relation_types: dict[str, int]
    backend_api_count: int
    frontend_api_call_count: int
    skipped_files: int
    parse_errors: int
    last_scan_at: datetime | None
