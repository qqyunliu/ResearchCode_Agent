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


def test_resolved_wrapper_entity_builds_request_relation() -> None:
    frontend = entity(
        "frontend:wrapped-video",
        "frontend_api_call",
        "POST",
        "/video/loadVideo",
    )
    frontend.metadata["resolution"] = "wrapper_default_method"
    backend = entity(
        "backend:load-video",
        "backend_api",
        "POST",
        "/video/loadVideo",
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


def test_repeated_api_candidates_create_one_request_relation() -> None:
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

    relations = build_relations(
        [frontend, frontend, backend, backend]
    )

    assert relations == (
        RelationCandidate(
            source_key=frontend.local_key,
            target_key=backend.local_key,
            relation_type="REQUESTS_API",
            confidence=1.0,
            metadata={},
        ),
    )


def java_entity(
    local_key: str,
    entity_type: str,
    name: str,
    qualified_name: str,
    metadata: dict[str, object],
    *,
    file_path: str,
) -> EntityCandidate:
    return EntityCandidate(
        local_key=local_key,
        entity_type=entity_type,
        name=name,
        qualified_name=qualified_name,
        file_path=file_path,
        start_line=1,
        end_line=1,
        content="",
        metadata=metadata,
    )


def service_entities(
    class_name: str,
    method_name: str,
    *,
    prefix: str,
) -> tuple[EntityCandidate, EntityCandidate]:
    service_class = java_entity(
        f"{prefix}:class",
        "java_class",
        class_name,
        class_name,
        {"is_service": True},
        file_path=f"{prefix}/{class_name}.java",
    )
    service_method = java_entity(
        f"{prefix}:method",
        "java_method",
        method_name,
        f"{class_name}.{method_name}",
        {
            "declaring_class": class_name,
            "invocations": [],
        },
        file_path=f"{prefix}/{class_name}.java",
    )
    return service_class, service_method


def controller_method(
    invocations: list[dict[str, str]],
) -> EntityCandidate:
    return java_entity(
        "controller:get-alert",
        "java_method",
        "getAlert",
        "AlertController.getAlert",
        {
            "declaring_class": "AlertController",
            "invocations": invocations,
        },
        file_path="controller/AlertController.java",
    )


def test_receiver_type_resolves_cross_file_service_call() -> None:
    service_class, service_method = service_entities(
        "AlertService",
        "findById",
        prefix="service",
    )
    controller = controller_method(
        [
            {
                "qualifier": "alertService",
                "method": "findById",
                "receiver_type": "AlertService",
            }
        ]
    )

    relations = build_relations(
        [controller, service_method, service_class]
    )

    assert relations == (
        RelationCandidate(
            source_key=controller.local_key,
            target_key=service_method.local_key,
            relation_type="CALLS_METHOD",
            confidence=0.8,
            metadata={
                "qualifier": "alertService",
                "resolution": "receiver_type",
            },
        ),
    )


def test_unique_method_name_fallback_has_lower_confidence() -> None:
    service_class, service_method = service_entities(
        "AlertService",
        "findById",
        prefix="service",
    )
    controller = controller_method(
        [{"qualifier": "service", "method": "findById"}]
    )

    relations = build_relations(
        [controller, service_class, service_method]
    )

    assert relations[0].target_key == service_method.local_key
    assert relations[0].confidence == 0.6
    assert relations[0].metadata["resolution"] == "unique_method_name"


def test_ambiguous_method_name_fallback_creates_no_relation() -> None:
    alert_class, alert_method = service_entities(
        "AlertService",
        "findById",
        prefix="alert",
    )
    audit_class, audit_method = service_entities(
        "AuditService",
        "findById",
        prefix="audit",
    )
    controller = controller_method(
        [{"qualifier": "service", "method": "findById"}]
    )

    relations = build_relations(
        [
            controller,
            alert_class,
            alert_method,
            audit_class,
            audit_method,
        ]
    )

    assert relations == ()


def test_non_service_method_is_not_a_call_target() -> None:
    helper_class = java_entity(
        "helper:class",
        "java_class",
        "AlertHelper",
        "AlertHelper",
        {"is_service": False},
        file_path="helper/AlertHelper.java",
    )
    helper_method = java_entity(
        "helper:method",
        "java_method",
        "findById",
        "AlertHelper.findById",
        {"declaring_class": "AlertHelper", "invocations": []},
        file_path="helper/AlertHelper.java",
    )
    controller = controller_method(
        [{"qualifier": "helper", "method": "findById"}]
    )

    assert build_relations(
        [controller, helper_class, helper_method]
    ) == ()


def test_duplicate_invocation_evidence_creates_one_call_edge() -> None:
    service_class, service_method = service_entities(
        "AlertService",
        "findById",
        prefix="service",
    )
    invocation = {
        "qualifier": "alertService",
        "method": "findById",
        "receiver_type": "AlertService",
    }
    controller = controller_method([invocation, invocation])

    relations = build_relations(
        [controller, service_class, service_method]
    )

    assert len(relations) == 1
