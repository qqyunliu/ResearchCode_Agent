import pytest

from app.retrieval.hybrid_search import fuse_search_hits
from app.retrieval.types import SearchHit


def hit(
    entity_id: int,
    score: float,
    source: str,
) -> SearchHit:
    return SearchHit(
        entity_id=entity_id,
        entity_type="java_method",
        name=f"method{entity_id}",
        qualified_name=f"Demo.method{entity_id}",
        file_path="src/Demo.java",
        start_line=entity_id,
        end_line=entity_id,
        content=f"void method{entity_id}() {{}}",
        metadata={},
        score=score,
        source=source,
    )


def test_normalizes_weights_and_deduplicates_hits() -> None:
    vector_hits = [
        hit(entity_id=1, score=0.9, source="vector"),
        hit(entity_id=2, score=0.6, source="vector"),
    ]
    keyword_hits = [
        hit(entity_id=2, score=1.0, source="keyword"),
        hit(entity_id=3, score=0.8, source="keyword"),
    ]

    results = fuse_search_hits(vector_hits, keyword_hits, limit=10)

    assert [result.entity_id for result in results] == [2, 1, 3]
    assert results[0].score == pytest.approx(
        0.7 * (0.6 / 0.9) + 0.3
    )
    assert results[1].score == pytest.approx(0.7)
    assert results[2].score == pytest.approx(0.3 * 0.8)
    assert {result.source for result in results} == {"hybrid"}


def test_ties_use_entity_id_and_limit_is_honored() -> None:
    results = fuse_search_hits(
        [
            hit(entity_id=8, score=0.5, source="vector"),
            hit(entity_id=3, score=0.5, source="vector"),
        ],
        [],
        limit=1,
    )

    assert [result.entity_id for result in results] == [3]


@pytest.mark.parametrize(
    ("vector_hits", "keyword_hits"),
    [
        ([], []),
        ([hit(1, 0.0, "vector")], []),
        ([], [hit(2, -1.0, "keyword")]),
    ],
)
def test_empty_or_non_positive_inputs_are_supported(
    vector_hits: list[SearchHit],
    keyword_hits: list[SearchHit],
) -> None:
    results = fuse_search_hits(vector_hits, keyword_hits, limit=10)

    if not vector_hits and not keyword_hits:
        assert results == []
    else:
        assert len(results) == 1
        assert results[0].score == 0.0
        assert results[0].source == "hybrid"
