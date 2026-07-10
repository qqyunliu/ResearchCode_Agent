import pytest

from app.errors import DomainError
from app.retrieval.hybrid_search import HybridSearchService, fuse_search_hits
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


def test_rewritten_query_is_used_by_both_retrieval_branches() -> None:
    calls = {}

    class Embeddings:
        def embed_query(self, text):
            calls["embedding"] = text
            return [1.0]

    class Store:
        def has_collection(self, project_id):
            return True

        def search(self, project_id, query_vector, limit):
            return []

    class Keywords:
        def search(self, project_id, query, limit):
            calls["keyword"] = query
            return []

    class Rewriter:
        def rewrite(self, query):
            calls["original"] = query
            return "alert list API controller"

    HybridSearchService(
        embeddings=Embeddings(),
        vector_store=Store(),
        keyword_search=Keywords(),
        rewriter=Rewriter(),
    ).search(1, "告警列表接口在哪里", 5)

    assert calls == {
        "original": "告警列表接口在哪里",
        "embedding": "alert list API controller",
        "keyword": "alert list API controller",
    }


def test_vector_failure_falls_back_to_keyword_hits() -> None:
    class Embeddings:
        def embed_query(self, text):
            raise TimeoutError("embedding timed out")

    class Store:
        def has_collection(self, project_id):
            return True

        def search(self, project_id, query_vector, limit):
            raise AssertionError("vector search must not run")

    class Keywords:
        def search(self, project_id, query, limit):
            return [hit(1, 0.8, "keyword")]

    results = HybridSearchService(
        embeddings=Embeddings(),
        vector_store=Store(),
        keyword_search=Keywords(),
    ).search(1, "alert", 5)

    assert [result.entity_id for result in results] == [1]
    assert results[0].source == "keyword_fallback"
    assert results[0].uncertainties == (
        "Vector retrieval was unavailable; keyword-only fallback was used.",
    )


def test_keyword_failure_keeps_vector_hits() -> None:
    class Embeddings:
        def embed_query(self, text):
            return [1.0]

    class Store:
        def has_collection(self, project_id):
            return True

        def search(self, project_id, query_vector, limit):
            return [hit(2, 0.9, "vector")]

    class Keywords:
        def search(self, project_id, query, limit):
            raise TimeoutError("keyword search timed out")

    results = HybridSearchService(
        embeddings=Embeddings(),
        vector_store=Store(),
        keyword_search=Keywords(),
    ).search(1, "alert", 5)

    assert [result.entity_id for result in results] == [2]
    assert results[0].source == "vector_fallback"
    assert results[0].uncertainties == (
        "Keyword retrieval was unavailable; vector-only fallback was used.",
    )


def test_missing_vector_index_is_not_hidden_by_fallback() -> None:
    class Store:
        def has_collection(self, project_id):
            return False

    with pytest.raises(DomainError) as raised:
        HybridSearchService(
            embeddings=object(),
            vector_store=Store(),
            keyword_search=object(),
        ).search(1, "alert", 5)

    assert raised.value.code == "VECTOR_INDEX_NOT_FOUND"


def test_both_retrieval_branches_failing_returns_domain_error() -> None:
    class Embeddings:
        def embed_query(self, text):
            raise TimeoutError("embedding timed out")

    class Store:
        def has_collection(self, project_id):
            return True

    class Keywords:
        def search(self, project_id, query, limit):
            raise RuntimeError("database unavailable")

    with pytest.raises(DomainError) as raised:
        HybridSearchService(
            embeddings=Embeddings(),
            vector_store=Store(),
            keyword_search=Keywords(),
        ).search(1, "alert", 5)

    assert raised.value.code == "RETRIEVAL_UNAVAILABLE"
    assert raised.value.status_code == 503


def test_keyword_domain_error_is_not_hidden_by_vector_fallback() -> None:
    class Embeddings:
        def embed_query(self, text):
            return [1.0]

    class Store:
        def has_collection(self, project_id):
            return True

        def search(self, project_id, query_vector, limit):
            return [hit(2, 0.9, "vector")]

    class Keywords:
        def search(self, project_id, query, limit):
            raise DomainError(
                code="PROJECT_NOT_FOUND",
                message="Project does not exist.",
                status_code=404,
            )

    with pytest.raises(DomainError) as raised:
        HybridSearchService(
            embeddings=Embeddings(),
            vector_store=Store(),
            keyword_search=Keywords(),
        ).search(1, "alert", 5)

    assert raised.value.code == "PROJECT_NOT_FOUND"
