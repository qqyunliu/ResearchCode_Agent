import argparse
from pathlib import Path

from app.parsers.base import EntityCandidate, RelationCandidate
from app.parsers.registry import ParserRegistry
from app.parsers.relation_builder import build_relations
from app.services.scanner import ProjectScanner


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Scan a project and print frontend-to-backend API chains."
    )
    argument_parser.add_argument("project_root", type=Path)
    args = argument_parser.parse_args()

    project_root = args.project_root.expanduser().resolve()
    scan_result = ProjectScanner().scan(project_root)
    registry = ParserRegistry()
    entities: list[EntityCandidate] = []
    parser_relations: list[RelationCandidate] = []

    for scanned_file in scan_result.files:
        result = registry.parse(scanned_file)
        entities.extend(result.entities)
        parser_relations.extend(result.relations)

    relations = build_relations(entities, parser_relations)
    entity_by_key = {entity.local_key: entity for entity in entities}
    handler_by_api = {
        relation.source_key: relation.target_key
        for relation in relations
        if relation.relation_type == "DEFINES_API"
    }
    calls_by_method: dict[str, list[RelationCandidate]] = {}
    for relation in relations:
        if relation.relation_type == "CALLS_METHOD":
            calls_by_method.setdefault(relation.source_key, []).append(
                relation
            )
    request_relations = [
        relation
        for relation in relations
        if relation.relation_type == "REQUESTS_API"
    ]

    print(f"Scanned files: {len(scan_result.files)}")
    print(f"Entities: {len(entities)}")
    print(f"Relations: {len(relations)}")
    print(f"Matched API chains: {len(request_relations)}")

    for relation in request_relations:
        frontend = entity_by_key[relation.source_key]
        backend = entity_by_key[relation.target_key]
        handler_key = handler_by_api.get(backend.local_key)
        handler = entity_by_key.get(handler_key) if handler_key else None
        print(f"  frontend: {frontend.file_path}:{frontend.start_line}")
        print(f"    {frontend.qualified_name}")
        print(
            f"      -[REQUESTS_API confidence={relation.confidence}]->"
        )
        print(f"    {backend.qualified_name}")
        if handler is not None:
            print(f"      -[DEFINES_API]-> {handler.qualified_name}")
            for call in calls_by_method.get(handler.local_key, []):
                service_method = entity_by_key.get(call.target_key)
                if service_method is not None:
                    print(
                        "        "
                        f"-[CALLS_METHOD confidence={call.confidence}]-> "
                        f"{service_method.qualified_name}"
                    )

    for issue in scan_result.issues:
        print(
            f"Scan issue: {issue.file_path} "
            f"{issue.reason_code} {issue.message}"
        )


if __name__ == "__main__":
    main()
