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
proxy.request({ url: proxy.Api.loadVideo })
fetch("/api/alerts")
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
        (candidate.callee, candidate.url_expression, candidate.method_expression)
        for candidate in result.frontend_request_candidates
    ] == [
        ("axios.get", '"/api/alerts/123"', "GET"),
        ("request.post", "`/api/alerts/${alertId}`", "POST"),
        ("request", '"/api/alerts/search"', '"POST"'),
        ("request", "dynamicUrl", "dynamicMethod"),
        ("proxy.request", "proxy.Api.loadVideo", None),
        ("fetch", '"/api/alerts"', "GET"),
    ]
    assert result.entities == ()
    assert result.relations == ()


def test_extracts_member_requests_from_typescript_file() -> None:
    source = """\
request.put("/api/devices/42", payload)
axios.patch('/api/devices/42/status', payload)
request.delete("/api/devices/42")
"""

    result = VueParser().parse("src/api.ts", source)

    assert [
        (candidate.callee, candidate.method_expression)
        for candidate in result.frontend_request_candidates
    ] == [
        ("request.put", "PUT"),
        ("axios.patch", "PATCH"),
        ("request.delete", "DELETE"),
    ]


def test_ignores_fully_dynamic_urls_and_methods() -> None:
    source = """\
axios.get(dynamicUrl)
request({ url: "/api/alerts", method: dynamicMethod })
request({ url: dynamicUrl, method: "GET" })
"""

    result = VueParser().parse("src/api.js", source)

    assert len(result.frontend_request_candidates) == 3
