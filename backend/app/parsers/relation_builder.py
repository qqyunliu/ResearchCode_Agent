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

    return tuple(relations)


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
