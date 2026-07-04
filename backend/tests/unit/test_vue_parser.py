from app.parsers.vue_parser import VueParser


VUE_SOURCE = """\
<template>
  <main>Alerts</main>
</template>

<script setup lang="ts">
axios.get("/api/alerts/123")
request.post(`/api/alerts/${alertId}`, payload)
request({ url: "/api/alerts/search", method: "POST" })
request({ url: dynamicUrl, method: dynamicMethod })
</script>
"""


def test_supports_frontend_languages() -> None:
    parser = VueParser()

    assert parser.supports("vue")
    assert parser.supports("javascript")
    assert parser.supports("typescript")
    assert not parser.supports("java")


def test_extracts_static_requests_from_vue_script_with_source_lines() -> None:
    result = VueParser().parse("src/AlertView.vue", VUE_SOURCE)

    assert [
        (entity.metadata["http_method"], entity.metadata["path"])
        for entity in result.entities
    ] == [
        ("GET", "/api/alerts/123"),
        ("POST", "/api/alerts/${alertId}"),
        ("POST", "/api/alerts/search"),
    ]
    assert [
        entity.metadata["normalized_path"] for entity in result.entities
    ] == [
        "/api/alerts/{param}",
        "/api/alerts/{param}",
        "/api/alerts/search",
    ]
    assert [entity.start_line for entity in result.entities] == [6, 7, 8]
    assert all(
        entity.entity_type == "frontend_api_call"
        for entity in result.entities
    )
    assert result.relations == ()


def test_extracts_member_requests_from_typescript_file() -> None:
    source = """\
request.put("/api/devices/42", payload)
axios.patch('/api/devices/42/status', payload)
request.delete("/api/devices/42")
"""

    result = VueParser().parse("src/api.ts", source)

    assert [
        (entity.metadata["http_method"], entity.metadata["normalized_path"])
        for entity in result.entities
    ] == [
        ("PUT", "/api/devices/{param}"),
        ("PATCH", "/api/devices/{param}/status"),
        ("DELETE", "/api/devices/{param}"),
    ]


def test_ignores_fully_dynamic_urls_and_methods() -> None:
    source = """\
axios.get(dynamicUrl)
request({ url: "/api/alerts", method: dynamicMethod })
request({ url: dynamicUrl, method: "GET" })
"""

    result = VueParser().parse("src/api.js", source)

    assert result.entities == ()
