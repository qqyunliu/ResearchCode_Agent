"""Shared, resumable infrastructure for Stage 2B evaluation runners.

The helpers in this module deliberately contain no backend configuration or
provider credentials.  Runners inject their real services, while this module
adds deterministic caching, call accounting, artifact verification, and
append-only checkpoints.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class ArtifactHashMismatchError(ValueError):
    """Raised before a run when an input artifact is not the pinned version."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of *path* without loading it all into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected_sha256: str) -> str:
    """Return the actual digest, refusing to continue when it is not pinned."""
    actual = sha256_file(path)
    expected = expected_sha256.strip().lower()
    if not hmac.compare_digest(actual, expected):
        raise ArtifactHashMismatchError(
            f"SHA-256 mismatch for {path}: expected {expected}, got {actual}"
        )
    return actual


_SECRET_KEY_FRAGMENTS = (
    "apikey",
    "authorization",
    "clientsecret",
    "privatekey",
    "secretaccesskey",
    "secretkey",
    "subscriptionkey",
    "password",
    "credential",
    "bearer",
)

_TOKEN_CREDENTIAL_QUALIFIERS = {
    "access",
    "api",
    "auth",
    "bearer",
    "id",
    "identity",
    "refresh",
    "secret",
    "session",
}


def _is_secret_key(key: object) -> bool:
    camel_separated = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key).strip()
    )
    normalized = re.sub(
        r"[^a-z0-9]+", "_", camel_separated.lower()
    ).strip("_")
    parts = {part for part in normalized.split("_") if part}
    compact = normalized.replace("_", "")
    if normalized == "token":
        return True
    if any(fragment in compact for fragment in _SECRET_KEY_FRAGMENTS):
        return True
    return "token" in parts and bool(parts & _TOKEN_CREDENTIAL_QUALIFIERS)


def sanitize_provider_metadata(value: Any) -> Any:
    """Deep-copy JSON-like metadata while dropping credential-bearing keys."""
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_provider_metadata(item)
            for key, item in value.items()
            if not _is_secret_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_provider_metadata(item) for item in value]
    if isinstance(value, str):
        return _sanitize_url(value)
    return value


_BEARER_VALUE_PATTERN = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_ASSIGNED_SECRET_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|authorization|access[_-]?token|token|password|secret)\s*[:=]\s*)"
    r"[^\s,;]+"
)
_EMBEDDED_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def sanitize_error_message(message: object) -> str:
    """Redact common credentials from an exception message before persistence."""
    value = str(message)
    value = _BEARER_VALUE_PATTERN.sub(r"\1[REDACTED]", value)
    value = _ASSIGNED_SECRET_PATTERN.sub(r"\1[REDACTED]", value)
    value = _EMBEDDED_URL_PATTERN.sub(
        lambda match: _sanitize_url(match.group(0)),
        value,
    )
    return value


def _sanitize_url(value: str) -> str:
    """Remove URL credentials while retaining non-secret query parameters."""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    query = urlencode(
        [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
         if not _is_secret_url_parameter(key)]
    )
    fragment = parsed.fragment
    if "=" in fragment:
        fragment = urlencode(
            [(key, item) for key, item in parse_qsl(fragment, keep_blank_values=True)
             if not _is_secret_url_parameter(key)]
        )
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, fragment))


def _is_secret_url_parameter(key: str) -> bool:
    return key.strip().lower() == "key" or _is_secret_key(key)


@dataclass(frozen=True)
class RunMetadata:
    """Serializable identity and reproducibility metadata for one run."""

    run_id: str
    dataset_path: str
    dataset_sha256: str
    providers: Mapping[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "dataset_path": self.dataset_path,
            "dataset_sha256": self.dataset_sha256,
            "providers": sanitize_provider_metadata(self.providers),
        }
        if self.started_at is not None:
            result["started_at"] = self.started_at
        if self.extra:
            result["extra"] = sanitize_provider_metadata(self.extra)
        return result


@dataclass
class CallCounters:
    """Provider-call totals; cache hits intentionally do not increment them."""

    calls: int = 0
    successes: int = 0
    failures: int = 0
    latency_seconds: float = 0.0

    def record_success(self, latency_seconds: float) -> None:
        self.calls += 1
        self.successes += 1
        self.latency_seconds += latency_seconds

    def record_failure(self, latency_seconds: float) -> None:
        self.calls += 1
        self.failures += 1
        self.latency_seconds += latency_seconds

    def to_dict(self) -> dict[str, int | float]:
        return {
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "latency_seconds": self.latency_seconds,
        }


class RecordingLlmClient:
    """LlmClient-compatible recorder for actual ``complete`` invocations."""

    def __init__(self, delegate: Any, counters: CallCounters | None = None) -> None:
        self.delegate = delegate
        self.provider_counters = counters or CallCounters()

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        write_ahead = _supports_write_ahead(self.provider_counters)
        attempt_id = self.provider_counters.begin_attempt() if write_ahead else None
        started = time.perf_counter()
        try:
            result = self.delegate.complete(system_prompt, user_prompt)
        except Exception:
            latency = time.perf_counter() - started
            if write_ahead:
                self.provider_counters.finish_attempt(attempt_id, "failure", latency)
            else:
                self.provider_counters.record_failure(latency)
            raise
        latency = time.perf_counter() - started
        if write_ahead:
            self.provider_counters.finish_attempt(attempt_id, "success", latency)
        else:
            self.provider_counters.record_success(latency)
        return result


def _supports_write_ahead(counters: Any) -> bool:
    return callable(getattr(counters, "begin_attempt", None)) and callable(
        getattr(counters, "finish_attempt", None)
    )


class _RecordingEmbeddingsEndpoint:
    def __init__(self, delegate: Any, counters: CallCounters) -> None:
        self.delegate = delegate
        self.provider_counters = counters

    def create(self, **request: object) -> Any:
        write_ahead = _supports_write_ahead(self.provider_counters)
        attempt_id = self.provider_counters.begin_attempt() if write_ahead else None
        started = time.perf_counter()
        try:
            response = self.delegate.create(**request)
        except Exception:
            latency = time.perf_counter() - started
            if write_ahead:
                self.provider_counters.finish_attempt(attempt_id, "failure", latency)
            else:
                self.provider_counters.record_failure(latency)
            raise
        latency = time.perf_counter() - started
        if write_ahead:
            self.provider_counters.finish_attempt(attempt_id, "success", latency)
        else:
            self.provider_counters.record_success(latency)
        return response


class RecordingOpenAIClient:
    """OpenAI-client proxy recording each real ``embeddings.create`` request."""

    def __init__(self, delegate: Any, counters: CallCounters | None = None) -> None:
        self.delegate = delegate
        self.provider_counters = counters or CallCounters()
        self.embeddings = _RecordingEmbeddingsEndpoint(
            delegate.embeddings, self.provider_counters
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


CheckpointKey = tuple[str, str, int]


def checkpoint_key(record: Mapping[str, Any]) -> CheckpointKey:
    """Extract the stable resume identity required by every raw record."""
    if not isinstance(record, Mapping):
        raise ValueError("checkpoint JSON must be an object")
    try:
        question_id = str(record["question_id"])
        variant = str(record["variant"])
        run_index = record["run_index"]
    except KeyError as error:
        raise ValueError(
            "checkpoint record requires question_id, variant, and run_index"
        ) from error
    if type(run_index) is not int or run_index < 0:
        raise ValueError("checkpoint record requires a non-negative integer run_index")
    return question_id, variant, run_index


class JsonlCheckpointWriter:
    """Append-only JSONL writer with duplicate-safe resume and durable lines."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.quarantine_path = Path(f"{self.path}.torn")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.completed_keys = self._load_completed_keys()
        self._stream = None

    def _load_completed_keys(self) -> set[CheckpointKey]:
        if not self.path.exists():
            return set()
        keys: set[CheckpointKey] = set()
        content = self.path.read_bytes()
        lines = content.splitlines(keepends=True)
        final_is_unterminated = bool(content) and not content.endswith((b"\n", b"\r"))
        for index, raw_line in enumerate(lines):
            line_number = index + 1
            payload = raw_line.rstrip(b"\r\n")
            if not payload.strip():
                continue
            try:
                record = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                if index == len(lines) - 1 and final_is_unterminated:
                    self._quarantine_torn_line(payload, b"".join(lines[:-1]))
                    return keys
                raise ValueError(
                    f"invalid JSONL checkpoint at {self.path}:{line_number}"
                ) from error
            keys.add(checkpoint_key(record))
        if final_is_unterminated:
            self._append_missing_newline()
        return keys

    def _quarantine_torn_line(self, torn: bytes, valid_prefix: bytes) -> None:
        with self.quarantine_path.open("wb") as quarantine:
            quarantine.write(torn)
            quarantine.flush()
            os.fsync(quarantine.fileno())
        with self.path.open("r+b") as target:
            target.seek(len(valid_prefix))
            target.truncate()
            target.flush()
            os.fsync(target.fileno())

    def _append_missing_newline(self) -> None:
        with self.path.open("ab") as target:
            target.write(b"\n")
            target.flush()
            os.fsync(target.fileno())

    def __enter__(self) -> "JsonlCheckpointWriter":
        self._stream = self.path.open("a", encoding="utf-8", newline="\n")
        return self

    def __exit__(self, *_: object) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def is_completed(self, question_id: str, variant: str, run_index: int) -> bool:
        key = checkpoint_key(
            {"question_id": question_id, "variant": variant, "run_index": run_index}
        )
        return key in self.completed_keys

    def append(self, record: Mapping[str, Any]) -> bool:
        """Durably append a new record; return False when already checkpointed."""
        key = checkpoint_key(record)
        if key in self.completed_keys:
            return False
        if self._stream is None:
            raise RuntimeError("JsonlCheckpointWriter must be used as a context manager")
        encoded = json.dumps(dict(record), ensure_ascii=False, separators=(",", ":"))
        self._stream.write(encoded + "\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self.completed_keys.add(key)
        return True


class _EmbeddingDelegate(Protocol):
    def embed_query(self, text: str) -> Sequence[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class CachedEmbeddingService:
    """EmbeddingService-compatible cache counting delegate operations.

    ``delegate_counters`` is not an HTTP-call counter: if the delegate batches
    or bypasses a remote provider, those details are invisible at this layer.
    Use ``RecordingOpenAIClient`` for provider request accounting.
    """

    def __init__(
        self,
        delegate: _EmbeddingDelegate,
        delegate_counters: CallCounters | None = None,
    ) -> None:
        self.delegate = delegate
        self.delegate_counters = delegate_counters or CallCounters()
        self._query_cache: dict[str, tuple[float, ...]] = {}

    def embed_query(self, text: str) -> list[float]:
        cached = self._query_cache.get(text)
        if cached is not None:
            return list(cached)
        started = time.perf_counter()
        try:
            vector = tuple(float(value) for value in self.delegate.embed_query(text))
        except Exception:
            self.delegate_counters.record_failure(time.perf_counter() - started)
            raise
        self.delegate_counters.record_success(time.perf_counter() - started)
        self._query_cache[text] = vector
        return list(vector)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        try:
            vectors = self.delegate.embed_documents(texts)
        except Exception:
            self.delegate_counters.record_failure(time.perf_counter() - started)
            raise
        self.delegate_counters.record_success(time.perf_counter() - started)
        return vectors


class _RewriteDelegate(Protocol):
    def rewrite(self, query: str) -> str: ...


class CachedQueryRewriter:
    """QueryRewriter cache counting delegate operations, not provider calls."""

    def __init__(
        self,
        delegate: _RewriteDelegate,
        delegate_counters: CallCounters | None = None,
    ) -> None:
        self.delegate = delegate
        self.delegate_counters = delegate_counters or CallCounters()
        self._cache: dict[str, str] = {}

    def rewrite(self, query: str) -> str:
        if query in self._cache:
            return self._cache[query]
        started = time.perf_counter()
        try:
            rewritten = self.delegate.rewrite(query)
        except Exception:
            self.delegate_counters.record_failure(time.perf_counter() - started)
            raise
        self.delegate_counters.record_success(time.perf_counter() - started)
        self._cache[query] = rewritten
        return rewritten
