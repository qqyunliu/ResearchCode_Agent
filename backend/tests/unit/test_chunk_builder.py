from types import SimpleNamespace

import pytest

from app.retrieval.chunk_builder import CodeChunkBuilder


def entity(**overrides) -> SimpleNamespace:
    values = {
        "id": 7,
        "entity_key": (
            "backend_api:src/AlertController.java:"
            "GET /api/alerts/{id}:4"
        ),
        "entity_type": "backend_api",
        "name": "GET /api/alerts/{id}",
        "qualified_name": "GET /api/alerts/{id}",
        "file_path": "src/AlertController.java",
        "start_line": 4,
        "end_line": 8,
        "content": (
            "Alert getAlert(Long id) { "
            "return alertService.findById(id); }"
        ),
        "metadata_json": (
            '{"normalized_path":"/api/alerts/{param}",'
            '"http_method":"GET"}'
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_builds_searchable_chunk_with_reference_fields() -> None:
    chunk = CodeChunkBuilder(max_content_chars=4000).build(entity())

    assert chunk.chunk_id == "entity:7"
    assert chunk.entity_id == 7
    assert chunk.file_path == "src/AlertController.java"
    assert chunk.metadata["http_method"] == "GET"
    assert chunk.searchable_text == (
        "Type: backend_api\n"
        "Name: GET /api/alerts/{id}\n"
        "Qualified name: GET /api/alerts/{id}\n"
        "File: src/AlertController.java\n"
        'Metadata: {"http_method": "GET", '
        '"normalized_path": "/api/alerts/{param}"}\n'
        "Code:\n"
        "Alert getAlert(Long id) { "
        "return alertService.findById(id); }"
    )


def test_truncates_only_content_and_keeps_identity_text() -> None:
    chunk = CodeChunkBuilder(max_content_chars=5).build(
        entity(content="0123456789")
    )

    assert chunk.content == "01234"
    assert chunk.qualified_name == "GET /api/alerts/{id}"
    assert chunk.searchable_text.endswith("Code:\n01234")


def test_build_many_preserves_entity_order() -> None:
    chunks = CodeChunkBuilder().build_many(
        [entity(id=9, name="second"), entity(id=3, name="first")]
    )

    assert [chunk.entity_id for chunk in chunks] == [9, 3]
    assert [chunk.name for chunk in chunks] == ["second", "first"]


def test_rejects_non_positive_content_limit() -> None:
    with pytest.raises(
        ValueError,
        match="max_content_chars must be greater than zero",
    ):
        CodeChunkBuilder(max_content_chars=0)
