from collections import defaultdict
from collections.abc import Iterable

from app.parsers.base import EntityCandidate, RelationCandidate

_ApiKey = tuple[str, str]
_RelationKey = tuple[str, str, str]


def build_relations(
    entities: Iterable[EntityCandidate],
    parser_relations: Iterable[RelationCandidate] = (),
) -> tuple[RelationCandidate, ...]:
    entity_list = list(entities)
    backend_index: dict[_ApiKey, list[EntityCandidate]] = defaultdict(list)
    frontend_calls: list[EntityCandidate] = []

    for entity in entity_list:
        if entity.entity_type == "backend_api":
            key = _api_key(entity)
            if key is not None:
                backend_index[key].append(entity)
        elif entity.entity_type == "frontend_api_call":
            frontend_calls.append(entity)

    relations: list[RelationCandidate] = []
    seen: set[_RelationKey] = set()
    for relation in parser_relations:
        _append_unique(relations, seen, relation)

    for frontend in frontend_calls:
        key = _api_key(frontend)
        if key is None:
            continue
        normalized_path, http_method = key
        matches = backend_index.get((normalized_path, http_method), [])
        confidence = 1.0
        if not matches:
            matches = backend_index.get((normalized_path, "ANY"), [])
            confidence = 0.8
        for backend in matches:
            _append_unique(
                relations,
                seen,
                RelationCandidate(
                    source_key=frontend.local_key,
                    target_key=backend.local_key,
                    relation_type="REQUESTS_API",
                    confidence=confidence,
                    metadata={},
                ),
            )

    _append_method_calls(entity_list, relations, seen)
    return tuple(relations)


def _append_method_calls(
    entities: list[EntityCandidate],
    relations: list[RelationCandidate],
    seen: set[_RelationKey],
) -> None:
    service_classes = {
        entity.qualified_name
        for entity in entities
        if (
            entity.entity_type == "java_class"
            and entity.metadata.get("is_service") is True
        )
    }
    service_aliases: dict[str, set[str]] = defaultdict(set)
    for class_name in service_classes:
        service_aliases[class_name].add(class_name)
        service_aliases[class_name.rsplit(".", 1)[-1]].add(class_name)

    service_methods: list[EntityCandidate] = []
    for entity in entities:
        if entity.entity_type != "java_method":
            continue
        declaring_class = entity.metadata.get("declaring_class")
        if (
            isinstance(declaring_class, str)
            and declaring_class in service_classes
        ):
            service_methods.append(entity)

    methods_by_name: dict[str, list[EntityCandidate]] = defaultdict(list)
    methods_by_class_and_name: dict[
        tuple[str, str],
        list[EntityCandidate],
    ] = defaultdict(list)
    for method in service_methods:
        declaring_class = method.metadata["declaring_class"]
        methods_by_name[method.name].append(method)
        methods_by_class_and_name[
            (str(declaring_class), method.name)
        ].append(method)

    for source in entities:
        if source.entity_type != "java_method":
            continue
        raw_invocations = source.metadata.get("invocations", [])
        if not isinstance(raw_invocations, list):
            continue
        for invocation in raw_invocations:
            if not isinstance(invocation, dict):
                continue
            method_name = invocation.get("method")
            qualifier = invocation.get("qualifier")
            receiver_type = invocation.get("receiver_type")
            if not isinstance(method_name, str):
                continue

            target: EntityCandidate | None = None
            confidence = 0.0
            resolution = ""
            if isinstance(receiver_type, str):
                candidates = [
                    method
                    for class_name in service_aliases.get(
                        receiver_type,
                        set(),
                    )
                    for method in methods_by_class_and_name.get(
                        (class_name, method_name),
                        [],
                    )
                ]
                if len(candidates) == 1:
                    target = candidates[0]
                    confidence = 0.8
                    resolution = "receiver_type"
            else:
                candidates = methods_by_name.get(method_name, [])
                if len(candidates) == 1:
                    target = candidates[0]
                    confidence = 0.6
                    resolution = "unique_method_name"

            if target is None:
                continue
            metadata = {"resolution": resolution}
            if isinstance(qualifier, str):
                metadata["qualifier"] = qualifier
            _append_unique(
                relations,
                seen,
                RelationCandidate(
                    source_key=source.local_key,
                    target_key=target.local_key,
                    relation_type="CALLS_METHOD",
                    confidence=confidence,
                    metadata=metadata,
                ),
            )


def _api_key(entity: EntityCandidate) -> _ApiKey | None:
    normalized_path = entity.metadata.get("normalized_path")
    http_method = entity.metadata.get("http_method")
    if not isinstance(normalized_path, str) or not isinstance(http_method, str):
        return None
    return normalized_path, http_method.upper()


def _append_unique(
    relations: list[RelationCandidate],
    seen: set[_RelationKey],
    relation: RelationCandidate,
) -> None:
    key = (
        relation.source_key,
        relation.target_key,
        relation.relation_type,
    )
    if key in seen:
        return
    seen.add(key)
    relations.append(relation)
