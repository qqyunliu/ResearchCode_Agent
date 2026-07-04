from dataclasses import FrozenInstanceError

import pytest

from app.parsers.base import (
    EntityCandidate,
    ParseResult,
    RelationCandidate,
    entity_key,
    source_slice,
)


def test_entity_key_is_deterministic() -> None:
    candidate = EntityCandidate(
        local_key="method:Detector.predict",
        entity_type="python_function",
        name="predict",
        qualified_name="Detector.predict",
        file_path="algorithm/detector.py",
        start_line=10,
        end_line=12,
        content="def predict():\n    pass",
        metadata={"arguments": []},
    )

    assert entity_key(candidate) == (
        "python_function:algorithm/detector.py:Detector.predict:10"
    )


def test_source_slice_uses_one_based_inclusive_lines() -> None:
    source = "first\nsecond\nthird\nfourth\n"

    assert source_slice(source, start_line=2, end_line=3) == "second\nthird"


def test_parse_result_defaults_to_empty_immutable_tuples() -> None:
    result = ParseResult()

    assert result.entities == ()
    assert result.relations == ()
    with pytest.raises(FrozenInstanceError):
        result.entities = ()  # type: ignore[misc]


def test_relation_candidate_records_graph_edge() -> None:
    relation = RelationCandidate(
        source_key="frontend:alert-list",
        target_key="backend:get-alerts",
        relation_type="REQUESTS_API",
        confidence=1.0,
        metadata={"normalized_path": "/api/alerts"},
    )

    assert relation.relation_type == "REQUESTS_API"
    assert relation.confidence == 1.0
