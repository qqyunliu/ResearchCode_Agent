from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodeChunk:
    chunk_id: str
    entity_id: int
    entity_key: str
    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]
    searchable_text: str


@dataclass(frozen=True, slots=True)
class SearchHit:
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
