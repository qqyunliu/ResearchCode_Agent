from app.parsers.registry import ParserRegistry
from app.services.scanner import ScannedFile


def scanned_file(language: str, content: str) -> ScannedFile:
    return ScannedFile(
        file_path=f"src/example.{language}",
        language=language,
        content=content,
        line_count=len(content.splitlines()),
        file_hash="test-hash",
        size_bytes=len(content.encode()),
    )


def test_registry_delegates_supported_languages() -> None:
    registry = ParserRegistry()

    java_result = registry.parse(
        scanned_file("java", "class Example { void run() {} }")
    )
    python_result = registry.parse(
        scanned_file("python", "def run():\n    pass\n")
    )
    frontend_result = registry.parse(
        scanned_file("typescript", 'axios.get("/api/health")')
    )

    assert [entity.entity_type for entity in java_result.entities] == [
        "java_class",
        "java_method",
    ]
    assert [entity.entity_type for entity in python_result.entities] == [
        "python_function",
    ]
    assert frontend_result.entities == ()
    assert [candidate.callee for candidate in frontend_result.frontend_request_candidates] == [
        "axios.get",
    ]


def test_registry_returns_empty_result_for_statistical_language() -> None:
    result = ParserRegistry().parse(
        scanned_file("json", '{"enabled": true}')
    )

    assert result.entities == ()
    assert result.relations == ()
