from types import SimpleNamespace

import pytest

from app.retrieval.embedding_service import (
    EmbeddingService,
    LocalSentenceTransformerProvider,
    OpenAICompatibleEmbeddingProvider,
)


class FakeProvider:
    def __init__(self) -> None:
        self.document_calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(texts)
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


class FakeArray:
    def __init__(self, values) -> None:
        self.values = values

    def tolist(self):
        return self.values


class FakeSentenceModel:
    def __init__(self) -> None:
        self.document_call = None
        self.query_call = None

    def encode_document(self, texts, **kwargs):
        self.document_call = (texts, kwargs)
        return FakeArray([[1, 2], [3.5, 4]])

    def encode_query(self, text, **kwargs):
        self.query_call = (text, kwargs)
        return FakeArray([5, 6.25])


class FakeEmbeddingsResource:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[3, 4]),
                SimpleNamespace(index=0, embedding=[1, 2]),
            ]
        )


class BatchAwareEmbeddingsResource:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        texts = kwargs["input"]
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=index,
                    embedding=[float(text[1:])],
                )
                for index, text in reversed(list(enumerate(texts)))
            ]
        )


def test_embedding_service_preserves_batch_order() -> None:
    provider = FakeProvider()
    service = EmbeddingService(provider)

    assert service.embed_documents(["a", "abcd"]) == [
        [1.0, 1.0],
        [4.0, 1.0],
    ]
    assert provider.document_calls == [["a", "abcd"]]


def test_embedding_service_skips_provider_for_empty_batch() -> None:
    provider = FakeProvider()

    assert EmbeddingService(provider).embed_documents([]) == []
    assert provider.document_calls == []


def test_embedding_service_embeds_query() -> None:
    assert EmbeddingService(FakeProvider()).embed_query("abc") == [
        3.0,
        1.0,
    ]


def test_local_provider_uses_document_and_query_encoding() -> None:
    model = FakeSentenceModel()
    provider = LocalSentenceTransformerProvider(
        "test-model",
        model=model,
    )

    documents = provider.embed_documents(["one", "two"])
    query = provider.embed_query("question")

    assert documents == [[1.0, 2.0], [3.5, 4.0]]
    assert query == [5.0, 6.25]
    assert model.document_call == (
        ["one", "two"],
        {
            "normalize_embeddings": True,
            "convert_to_numpy": True,
        },
    )
    assert model.query_call == (
        "question",
        {
            "normalize_embeddings": True,
            "convert_to_numpy": True,
        },
    )


def test_openai_provider_restores_response_order() -> None:
    embeddings = FakeEmbeddingsResource()
    client = SimpleNamespace(embeddings=embeddings)
    provider = OpenAICompatibleEmbeddingProvider(
        model_name="embedding-model",
        api_key="test-key",
        client=client,
    )

    assert provider.embed_documents(["first", "second"]) == [
        [1.0, 2.0],
        [3.0, 4.0],
    ]
    assert embeddings.calls == [
        {
            "model": "embedding-model",
            "input": ["first", "second"],
        }
    ]


def test_openai_provider_sends_configured_dimensions() -> None:
    embeddings = FakeEmbeddingsResource()
    provider = OpenAICompatibleEmbeddingProvider(
        "embedding-3", "key", dimensions=1024,
        client=SimpleNamespace(embeddings=embeddings),
    )
    provider.embed_query("告警接口")
    assert embeddings.calls == [{
        "model": "embedding-3",
        "input": ["告警接口"],
        "dimensions": 1024,
    }]


def test_openai_provider_batches_documents_at_64_and_preserves_order() -> None:
    embeddings = BatchAwareEmbeddingsResource()
    provider = OpenAICompatibleEmbeddingProvider(
        "embedding-3",
        "key",
        dimensions=1024,
        client=SimpleNamespace(embeddings=embeddings),
    )
    texts = [f"t{index}" for index in range(130)]

    vectors = provider.embed_documents(texts)

    assert [len(call["input"]) for call in embeddings.calls] == [64, 64, 2]
    assert [vector[0] for vector in vectors] == list(map(float, range(130)))
    assert all(call["dimensions"] == 1024 for call in embeddings.calls)


def test_openai_provider_requires_api_key() -> None:
    with pytest.raises(
        ValueError,
        match="RCA_EMBEDDING_API_KEY is required",
    ):
        OpenAICompatibleEmbeddingProvider(
            model_name="embedding-model",
            api_key=None,
        )


def test_openai_provider_maps_external_failure_to_domain_error() -> None:
    from app.errors import DomainError

    class FailingEmbeddings:
        def create(self, **kwargs):
            raise RuntimeError("secret provider detail")

    provider = OpenAICompatibleEmbeddingProvider(
        "embedding-3",
        "test-key",
        dimensions=1024,
        client=SimpleNamespace(embeddings=FailingEmbeddings()),
    )

    with pytest.raises(DomainError) as error:
        provider.embed_query("告警接口")
    assert error.value.code == "EMBEDDING_REQUEST_FAILED"
    assert error.value.status_code == 502
    assert "secret provider detail" not in error.value.message
