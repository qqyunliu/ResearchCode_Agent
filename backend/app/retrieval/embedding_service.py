from collections.abc import Sequence
from typing import Any, Protocol

from app.errors import DomainError

API_EMBEDDING_BATCH_SIZE = 64

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
        dimensions: int | None = None,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("RCA_EMBEDDING_API_KEY is required")
        self.model_name = model_name
        if dimensions is not None and dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        self.dimensions = dimensions
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
        self.client = client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), API_EMBEDDING_BATCH_SIZE):
            batch = texts[start : start + API_EMBEDDING_BATCH_SIZE]
            request = {
                "model": self.model_name,
                "input": batch,
            }
            if self.dimensions is not None:
                request["dimensions"] = self.dimensions
            response = self._create(request)
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(
                _float_vector(item.embedding) for item in ordered
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        request = {"model": self.model_name, "input": [text]}
        if self.dimensions is not None:
            request["dimensions"] = self.dimensions
        response = self._create(request)
        first = min(response.data, key=lambda item: item.index)
        return _float_vector(first.embedding)

    def _create(self, request: dict[str, object]) -> Any:
        try:
            return self.client.embeddings.create(**request)
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="EMBEDDING_REQUEST_FAILED",
                message="The external embedding request failed.",
                status_code=502,
            ) from error


def _as_list(value: Any) -> Any:
    tolist = getattr(value, "tolist", None)
    return tolist() if callable(tolist) else value


def _float_vector(vector: Sequence[float]) -> list[float]:
    result = [float(value) for value in vector]
    if not result:
        raise ValueError("embedding provider returned an empty vector")
    return result
