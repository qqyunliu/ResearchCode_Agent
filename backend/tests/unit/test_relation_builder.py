from app.parsers.base import EntityCandidate, RelationCandidate
from app.parsers.relation_builder import build_relations


def entity(
    local_key: str,
    entity_type: str,
    method: str,
    normalized_path: str,
) -> EntityCandidate:
    return EntityCandidate(
        local_key=local_key,
        entity_type=entity_type,
        name=local_key,
        qualified_name=local_key,
        file_path="example",
        start_line=1,
        end_line=1,
        content="",
        metadata={
            "http_method": method,
            "normalized_path": normalized_path,
        },
    )


def test_exact_method_match_creates_high_confidence_relation() -> None:
    frontend = entity(
        "frontend:get-alert",
        "frontend_api_call",
        "GET",
        "/api/alerts/{param}",
    )
    backend = entity(
        "backend:get-alert",
        "backend_api",
        "GET",
        "/api/alerts/{param}",
    )

    relations = build_relations([frontend, backend])

    assert relations == (
        RelationCandidate(
            source_key=frontend.local_key,
            target_key=backend.local_key,
            relation_type="REQUESTS_API",
            confidence=1.0,
            metadata={},
        ),
    )


def test_any_method_is_used_only_as_fallback() -> None:
    frontend = entity(
        "frontend:config",
        "frontend_api_call",
        "POST",
        "/api/config",
    )
    exact_backend = entity(
        "backend:config-post",
        "backend_api",
        "POST",
        "/api/config",
    )
    any_backend = entity(
        "backend:config-any",
        "backend_api",
        "ANY",
        "/api/config",
    )

    exact_relations = build_relations(
        [frontend, any_backend, exact_backend]
    )
    fallback_relations = build_relations([frontend, any_backend])

    assert [relation.target_key for relation in exact_relations] == [
        exact_backend.local_key
    ]
    assert fallback_relations[0].target_key == any_backend.local_key
    assert fallback_relations[0].confidence == 0.8


def test_unmatched_frontend_call_creates_no_relation() -> None:
    frontend = entity(
        "frontend:missing",
        "frontend_api_call",
        "GET",
        "/api/missing",
    )
    backend = entity(
        "backend:alerts",
        "backend_api",
        "GET",
        "/api/alerts",
    )

    assert build_relations([frontend, backend]) == ()


def test_parser_relations_are_combined_and_deduplicated() -> None:
    existing = RelationCandidate(
        source_key="class:AlertController",
        target_key="method:getAlert",
        relation_type="CONTAINS",
        confidence=1.0,
        metadata={},
    )

    relations = build_relations([], [existing, existing])

    assert relations == (existing,)
