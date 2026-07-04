from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

EntityType: TypeAlias = Literal[
    "java_class",
    "java_method",
    "backend_api",
    "frontend_api_call",
    "python_class",
    "python_function",
]

RelationType: TypeAlias = Literal[
    "CONTAINS",
    "DEFINES_API",
    "REQUESTS_API",
]


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    local_key: str
    entity_type: EntityType
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class RelationCandidate:
    source_key: str
    target_key: str
    relation_type: RelationType
    confidence: float
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class ParseResult:
    entities: tuple[EntityCandidate, ...] = ()
    relations: tuple[RelationCandidate, ...] = ()


class SourceParser(Protocol):
    def supports(self, language: str) -> bool:
        ...

    def parse(self, file_path: str, source: str) -> ParseResult:
        ...


def entity_key(candidate: EntityCandidate) -> str:
    return (
        f"{candidate.entity_type}:{candidate.file_path}:"
        f"{candidate.qualified_name}:{candidate.start_line}"
    )


def source_slice(source: str, start_line: int, end_line: int) -> str:
    if start_line < 1:
        raise ValueError("start_line must be one-based")
    if end_line < start_line:
        raise ValueError("end_line must be greater than or equal to start_line")
    return "\n".join(source.splitlines()[start_line - 1 : end_line])
