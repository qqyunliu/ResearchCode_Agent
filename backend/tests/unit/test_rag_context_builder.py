import pytest

from app.rag.context_builder import RagContextBuilder
from app.retrieval.types import SearchHit


def hit(
    entity_id: int,
    *,
    file_path: str,
    start_line: int,
    end_line: int,
    entity_type: str,
    qualified_name: str,
    content: str,
) -> SearchHit:
    return SearchHit(
        entity_id=entity_id,
        entity_type=entity_type,
        name=qualified_name.rsplit(".", 1)[-1],
        qualified_name=qualified_name,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        content=content,
        metadata={},
        score=1.0,
        source="hybrid",
    )


def alert_hit() -> SearchHit:
    return hit(
        5,
        file_path="src/AlertController.java",
        start_line=4,
        end_line=8,
        entity_type="java_method",
        qualified_name="AlertController.getAlert",
        content=(
            "Alert getAlert(Long id) { "
            "return alertService.findById(id); }"
        ),
    )


def service_hit() -> SearchHit:
    return hit(
        9,
        file_path="src/AlertService.java",
        start_line=3,
        end_line=5,
        entity_type="java_method",
        qualified_name="AlertService.findById",
        content="Alert findById(Long id) { return null; }",
    )


def test_builds_ranked_context_and_structured_references() -> None:
    context = RagContextBuilder().build([alert_hit(), service_hit()])

    first_block = (
        "[1] src/AlertController.java:4-8\n"
        "Type: java_method\n"
        "Name: AlertController.getAlert\n"
        "Code:\n"
        "Alert getAlert(Long id) { "
        "return alertService.findById(id); }"
    )
    second_block = (
        "[2] src/AlertService.java:3-5\n"
        "Type: java_method\n"
        "Name: AlertService.findById\n"
        "Code:\n"
        "Alert findById(Long id) { return null; }"
    )
    assert context.text == f"{first_block}\n\n{second_block}"
    assert [reference.citation for reference in context.references] == [1, 2]
    assert context.references[0].entity_id == 5
    assert context.references[0].file_path == "src/AlertController.java"
    assert context.references[0].start_line == 4
    assert context.references[0].end_line == 8
    assert context.references[0].entity_type == "java_method"
    assert (
        context.references[0].qualified_name
        == "AlertController.getAlert"
    )


def test_stops_before_a_complete_block_would_exceed_budget() -> None:
    first_only = RagContextBuilder().build([alert_hit()]).text
    builder = RagContextBuilder(max_context_chars=len(first_only))

    context = builder.build([alert_hit(), service_hit()])

    assert context.text == first_only
    assert len(context.text) <= len(first_only)
    assert [reference.entity_id for reference in context.references] == [5]
    assert "[2]" not in context.text


def test_does_not_split_header_when_first_hit_cannot_fit() -> None:
    header = (
        "[1] src/AlertController.java:4-8\n"
        "Type: java_method\n"
        "Name: AlertController.getAlert\n"
        "Code:\n"
    )
    context = RagContextBuilder(
        max_context_chars=len(header) - 1
    ).build([alert_hit()])

    assert context.text == ""
    assert context.references == ()
    assert "[1]" not in context.text


def test_empty_hits_return_empty_context() -> None:
    context = RagContextBuilder().build([])

    assert context.text == ""
    assert context.references == ()


def test_rejects_non_positive_context_budget() -> None:
    with pytest.raises(
        ValueError,
        match="max_context_chars must be greater than zero",
    ):
        RagContextBuilder(max_context_chars=0)
