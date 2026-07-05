from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GraphNode:
    entity_id: int
    label: str
    entity_type: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class GraphEdge:
    relation_id: int
    source_id: int
    target_id: int
    relation_type: str
    confidence: float
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class GraphResult:
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
