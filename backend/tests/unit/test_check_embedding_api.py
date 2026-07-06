from scripts.check_embedding_api import check, cosine


class FakeProvider:
    def embed_documents(self, texts):
        assert len(texts) == 3
        return [
            [1.0, 0.0] + [0.0] * 1022,
            [0.9, 0.1] + [0.0] * 1022,
            [0.0, 1.0] + [0.0] * 1022,
        ]

    def embed_query(self, text):
        raise AssertionError


def test_check_validates_cross_language_similarity() -> None:
    related, unrelated = check(FakeProvider(), 1024)
    assert related > unrelated


def test_cosine_rejects_zero_vector() -> None:
    import pytest
    with pytest.raises(ValueError, match="non-zero"):
        cosine([0.0], [1.0])
