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
    assert len(
        [
            relation
            for relation in result.relations
            if relation.relation_type == "CONTAINS"
        ]
    ) == 2
    assert len(
        [
            relation
            for relation in result.relations
            if relation.relation_type == "DEFINES_API"
        ]
    ) == 3


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
