from dataclasses import dataclass
from enum import Enum

from app.schemas.agent import ContextReferenceRead
from app.schemas.graph import GraphEdgeRead, GraphNodeRead


class TaskType(str, Enum):
    CODE_QA = "CODE_QA"
    TRACE_CHAIN = "TRACE_CHAIN"
    CHANGE_PLAN = "CHANGE_PLAN"


@dataclass(frozen=True)
class AgentResult:
    task_type: TaskType
    answer: str
    references: tuple[ContextReferenceRead, ...] = ()
    graph_nodes: tuple[GraphNodeRead, ...] = ()
    graph_edges: tuple[GraphEdgeRead, ...] = ()
    uncertainties: tuple[str, ...] = ()
