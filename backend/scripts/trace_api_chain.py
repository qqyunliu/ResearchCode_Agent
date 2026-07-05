import argparse

from app.core.database import SessionLocal
from app.errors import DomainError
from app.graph.query_service import (
    CHAIN_RELATION_TYPES,
    GraphQueryService,
)
from app.graph.types import GraphNode, GraphResult


def ordered_nodes(graph: GraphResult) -> list[GraphNode]:
    node_by_id = {node.entity_id: node for node in graph.nodes}
    ordered_ids: list[int] = []

    def append(entity_id: int) -> None:
        if entity_id in node_by_id and entity_id not in ordered_ids:
            ordered_ids.append(entity_id)

    request_edges = [
        edge
        for edge in graph.edges
        if edge.relation_type == "REQUESTS_API"
    ]
    definition_edges = [
        edge
        for edge in graph.edges
        if edge.relation_type == "DEFINES_API"
    ]
    call_edges = [
        edge
        for edge in graph.edges
        if edge.relation_type == "CALLS_METHOD"
    ]

    for edge in request_edges:
        append(edge.source_id)
    for edge in request_edges:
        append(edge.target_id)
    for edge in definition_edges:
        append(edge.source_id)
        append(edge.target_id)
    for edge in call_edges:
        append(edge.source_id)
        append(edge.target_id)
    for node in graph.nodes:
        append(node.entity_id)
    return [node_by_id[entity_id] for entity_id in ordered_ids]


def print_graph(graph: GraphResult) -> None:
    print(f"Nodes: {len(graph.nodes)}")
    for index, node in enumerate(ordered_nodes(graph), start=1):
        print(
            f"  [{index}] {node.entity_type} "
            f"{node.qualified_name}"
        )
        print(
            f"      {node.file_path}:"
            f"{node.start_line}-{node.end_line}"
        )

    print(f"Edges: {len(graph.edges)}")
    node_by_id = {node.entity_id: node for node in graph.nodes}
    for edge in graph.edges:
        source = node_by_id[edge.source_id]
        target = node_by_id[edge.target_id]
        print(
            f"  {source.qualified_name} "
            f"-[{edge.relation_type} "
            f"confidence={edge.confidence}]-> "
            f"{target.qualified_name}"
        )

    present = {edge.relation_type for edge in graph.edges}
    missing = [
        relation_type
        for relation_type in CHAIN_RELATION_TYPES
        if relation_type not in present
    ]
    if missing:
        print(f"Missing segments: {', '.join(missing)}")
    else:
        print("Missing segments: none")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Print one persisted frontend-to-service API chain "
            "without embeddings or an LLM."
        )
    )
    parser.add_argument("project_id", type=int)
    parser.add_argument("method")
    parser.add_argument("api_path")
    args = parser.parse_args()

    with SessionLocal() as session:
        try:
            graph = GraphQueryService(session).find_api_chain(
                args.project_id,
                args.method,
                args.api_path,
            )
        except DomainError as error:
            parser.error(f"{error.code}: {error.message}")
    print_graph(graph)


if __name__ == "__main__":
    main()
