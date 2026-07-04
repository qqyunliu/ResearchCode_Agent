from collections.abc import Sequence
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.provider.embed_documents(texts)
        if len(vectors) != len(texts):
            raise ValueError(
                "embedding provider returned an unexpected vector count"
            )
        return [_float_vector(vector) for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return _float_vector(self.provider.embed_query(text))


class LocalSentenceTransformerProvider:
    def __init__(
        self,
        model_name: str,
        *,
        model: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self._model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        encoded = self._get_model().encode_document(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [
            _float_vector(vector)
            for vector in _as_list(encoded)
        ]

    def embed_query(self, text: str) -> list[float]:
        encoded = self._get_model().encode_query(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return _float_vector(_as_list(encoded))

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        model_name: str,
        api_key: str | None,
        *,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("RCA_EMBEDDING_API_KEY is required")
        self.model_name = model_name
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
        self.client = client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [_float_vector(item.embedding) for item in ordered]

    def embed_query(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=[text],
        )
        first = min(response.data, key=lambda item: item.index)
        return _float_vector(first.embedding)


def _as_list(value: Any) -> Any:
    tolist = getattr(value, "tolist", None)
    return tolist() if callable(tolist) else value


def _float_vector(vector: Sequence[float]) -> list[float]:
    result = [float(value) for value in vector]
    if not result:
        raise ValueError("embedding provider returned an empty vector")
    return result
