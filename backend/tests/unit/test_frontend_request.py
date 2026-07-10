from app.parsers.base import FrontendRequestCandidate
from app.parsers.frontend_request import FrontendRequestResolver
from app.services.scanner import ScannedFile


def scanned_file(path: str, content: str) -> ScannedFile:
    return ScannedFile(
        file_path=path,
        language="javascript",
        content=content,
        line_count=len(content.splitlines()),
        file_hash=path,
        size_bytes=len(content.encode()),
    )


def candidate(
    *,
    callee: str,
    url_expression: str,
    method_expression: str | None = None,
) -> FrontendRequestCandidate:
    return FrontendRequestCandidate(
        file_path="src/View.vue",
        start_line=7,
        end_line=7,
        start_byte=20,
        content=f"{callee}({url_expression})",
        callee=callee,
        url_expression=url_expression,
        method_expression=method_expression,
    )


def test_resolves_literal_url_and_explicit_method() -> None:
    entities, warnings = FrontendRequestResolver(()).resolve([
        candidate(
            callee="axios",
            url_expression='"/api/alerts/42"',
            method_expression='"POST"',
        )
    ])

    assert [entity.qualified_name for entity in entities] == [
        "POST /api/alerts/42"
    ]
    assert entities[0].metadata["normalized_path"] == "/api/alerts/{param}"
    assert warnings == []


def test_resolves_unique_constant_and_wrapper_default_method() -> None:
    files = (
        scanned_file(
            "src/utils/Api.js",
            'export const Api = { loadVideo: "/video/loadVideo" }',
        ),
        scanned_file(
            "src/utils/Request.js",
            "export const request = (config) => instance.post(config.url)",
        ),
    )
    entities, warnings = FrontendRequestResolver(files).resolve([
        candidate(
            callee="proxy.request",
            url_expression="proxy.Api.loadVideo",
        )
    ])

    assert [entity.qualified_name for entity in entities] == [
        "POST /video/loadVideo"
    ]
    assert entities[0].metadata["resolution"] == "wrapper_default_method"
    assert warnings == []


def test_resolves_multiline_wrapper_with_destructured_url() -> None:
    files = (
        scanned_file(
            "src/utils/Api.js",
            'const Api = { loadVideo: "/video/loadVideo" }',
        ),
        scanned_file(
            "src/utils/Request.js",
            """const request = (config) => {
  const { url, params } = config
  const formData = new FormData()
  return instance.post(url, formData)
}""",
        ),
    )

    entities, warnings = FrontendRequestResolver(files).resolve([
        candidate(
            callee="proxy.request",
            url_expression="proxy.Api.loadVideo",
        )
    ])

    assert [entity.qualified_name for entity in entities] == [
        "POST /video/loadVideo"
    ]
    assert warnings == []


def test_dynamic_or_ambiguous_values_do_not_create_entities() -> None:
    files = (
        scanned_file("src/one.js", 'const Api = { load: "/one" }'),
        scanned_file("src/two.js", 'const Api = { load: "/two" }'),
    )
    entities, warnings = FrontendRequestResolver(files).resolve([
        candidate(callee="proxy.request", url_expression="proxy.Api.load"),
        candidate(
            callee="fetch",
            url_expression="dynamicUrl",
            method_expression="GET",
        ),
    ])

    assert entities == []
    assert [warning.reason_code for warning in warnings] == [
        "FRONTEND_REQUEST_AMBIGUOUS_CONSTANT",
        "FRONTEND_REQUEST_DYNAMIC_URL",
    ]
