from app.parsers.java_parser import JavaParser


JAVA_SOURCE = """\
@RestController
@RequestMapping("/api/alerts")
class AlertController {
    @GetMapping("/{id}")
    Alert getAlert(Long id) {
        return null;
    }

    @RequestMapping(
        value = {"/search", "/query"},
        method = RequestMethod.POST,
        produces = "application/json"
    )
    List<Alert> search() {
        return List.of();
    }
}
"""


def test_supports_only_java() -> None:
    parser = JavaParser()

    assert parser.supports("java")
    assert not parser.supports("python")


def test_extracts_classes_methods_spring_apis_and_relations() -> None:
    result = JavaParser().parse("src/AlertController.java", JAVA_SOURCE)

    classes = [
        entity for entity in result.entities if entity.entity_type == "java_class"
    ]
    methods = [
        entity for entity in result.entities if entity.entity_type == "java_method"
    ]
    apis = [
        entity for entity in result.entities if entity.entity_type == "backend_api"
    ]

    assert [entity.qualified_name for entity in classes] == ["AlertController"]
    assert [entity.qualified_name for entity in methods] == [
        "AlertController.getAlert",
        "AlertController.search",
    ]
    assert {
        (entity.metadata["http_method"], entity.metadata["path"])
        for entity in apis
    } == {
        ("GET", "/api/alerts/{id}"),
        ("POST", "/api/alerts/search"),
        ("POST", "/api/alerts/query"),
    }
    assert {
        entity.metadata["normalized_path"] for entity in apis
    } == {
        "/api/alerts/{param}",
        "/api/alerts/search",
        "/api/alerts/query",
    }
    assert {
        (
            entity.metadata["controller_class"],
            entity.metadata["handler_method"],
            entity.metadata["http_method"],
            entity.metadata["path"],
            entity.metadata["normalized_path"],
        )
        for entity in apis
    } == {
        (
            "AlertController",
            "getAlert",
            "GET",
            "/api/alerts/{id}",
            "/api/alerts/{param}",
        ),
        (
            "AlertController",
            "search",
            "POST",
            "/api/alerts/search",
            "/api/alerts/search",
        ),
        (
            "AlertController",
            "search",
            "POST",
            "/api/alerts/query",
            "/api/alerts/query",
        ),
    }

    contains = [
        relation
        for relation in result.relations
        if relation.relation_type == "CONTAINS"
    ]
    defines_api = [
        relation
        for relation in result.relations
        if relation.relation_type == "DEFINES_API"
    ]

    assert len(contains) == len(methods) == 2
    assert len(defines_api) == len(apis) == 3
    assert len(
        {
            (
                relation.source_key,
                relation.target_key,
                relation.relation_type,
            )
            for relation in result.relations
        }
    ) == len(result.relations)


def test_request_mapping_without_method_is_any() -> None:
    source = """\
@Controller
class ConfigController {
    @RequestMapping(path = "/config")
    String config() { return "ok"; }
}
"""

    result = JavaParser().parse("ConfigController.java", source)
    api = next(
        entity for entity in result.entities if entity.entity_type == "backend_api"
    )

    assert api.metadata["http_method"] == "ANY"
    assert api.metadata["path"] == "/config"


def test_service_methods_do_not_become_http_apis() -> None:
    source = """\
@Service
class AlertService {
    Alert find() { return null; }
}
"""

    result = JavaParser().parse("AlertService.java", source)

    assert [entity.entity_type for entity in result.entities] == [
        "java_class",
        "java_method",
    ]


def test_extracts_constructor_injected_service_invocation() -> None:
    source = """\
@RestController
class AlertController {
    private final AlertService alertService;

    AlertController(AlertService alertService) {
        this.alertService = alertService;
    }

    Alert getAlert(Long id) {
        validate(id);
        return alertService.findById(id);
    }
}
"""

    result = JavaParser().parse("AlertController.java", source)
    method = next(
        entity
        for entity in result.entities
        if entity.qualified_name == "AlertController.getAlert"
    )

    assert method.metadata["declaring_class"] == "AlertController"
    assert method.metadata["invocations"] == [
        {
            "qualifier": "alertService",
            "method": "findById",
            "receiver_type": "AlertService",
        }
    ]


def test_extracts_annotated_field_injections() -> None:
    source = """\
@RestController
class AlertController {
    @Autowired
    private AlertService alertService;

    @Resource
    private AuditService auditService;

    void execute() {
        alertService.findById(1L);
        auditService.record();
    }
}
"""

    result = JavaParser().parse("AlertController.java", source)
    method = next(
        entity
        for entity in result.entities
        if entity.qualified_name == "AlertController.execute"
    )

    assert method.metadata["invocations"] == [
        {
            "qualifier": "alertService",
            "method": "findById",
            "receiver_type": "AlertService",
        },
        {
            "qualifier": "auditService",
            "method": "record",
            "receiver_type": "AuditService",
        },
    ]


def test_nested_classes_keep_dependency_evidence_separate() -> None:
    source = """\
class OuterController {
    @Autowired
    private OuterService outerService;

    void outer() {
        outerService.run();
    }

    class InnerController {
        @Resource
        private InnerService innerService;

        void inner() {
            innerService.run();
            outerService.run();
        }
    }
}
"""

    result = JavaParser().parse("Nested.java", source)
    methods = {
        entity.qualified_name: entity
        for entity in result.entities
        if entity.entity_type == "java_method"
    }

    assert methods["OuterController.outer"].metadata["invocations"] == [
        {
            "qualifier": "outerService",
            "method": "run",
            "receiver_type": "OuterService",
        }
    ]
    assert methods[
        "OuterController.InnerController.inner"
    ].metadata["invocations"] == [
        {
            "qualifier": "innerService",
            "method": "run",
            "receiver_type": "InnerService",
        }
    ]
