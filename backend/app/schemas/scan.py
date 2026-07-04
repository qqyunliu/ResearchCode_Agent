from typing import Literal

from pydantic import BaseModel


class ScanSummary(BaseModel):
    project_id: int
    status: Literal["ready"]
    files_indexed: int
    entities_indexed: int
    relations_indexed: int
    files_skipped: int
    parse_errors: int
