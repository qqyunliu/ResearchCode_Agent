from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest


RUNNERS_DIR = Path(__file__).resolve().parents[2] / "runners"
if str(RUNNERS_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNERS_DIR))

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_cached_embedding_reuses_success_for_each_distinct_query() -> None:
    from stage2b_common import CachedEmbeddingService

    class Delegate:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def embed_query(self, text: str) -> list[float]:
            self.queries.append(text)
            return [float(len(text))]

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(text))] for text in texts]

    delegate = Delegate()
    cached = CachedEmbeddingService(delegate)

    first = cached.embed_query("alert")
    first.append(999.0)

    assert cached.embed_query("alert") == [5.0]
    assert cached.embed_query("trace") == [5.0]
    assert delegate.queries == ["alert", "trace"]
    assert cached.delegate_counters.to_dict()["calls"] == 2
    assert cached.delegate_counters.to_dict()["successes"] == 2


def test_cached_embedding_counts_failures_without_caching_them() -> None:
    from stage2b_common import CachedEmbeddingService

    class FlakyDelegate:
        def __init__(self) -> None:
            self.calls = 0

        def embed_query(self, text: str) -> list[float]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary provider failure")
            return [1.0]

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0] for _ in texts]

    delegate = FlakyDelegate()
    cached = CachedEmbeddingService(delegate)

    with pytest.raises(RuntimeError, match="temporary"):
        cached.embed_query("same query")

    assert cached.embed_query("same query") == [1.0]
    assert delegate.calls == 2
    assert cached.delegate_counters.to_dict()["failures"] == 1
    assert cached.delegate_counters.to_dict()["successes"] == 1


def test_cached_rewriter_reuses_success_but_retries_failure() -> None:
    from stage2b_common import CachedQueryRewriter

    class Delegate:
        def __init__(self) -> None:
            self.calls: dict[str, int] = {}

        def rewrite(self, query: str) -> str:
            self.calls[query] = self.calls.get(query, 0) + 1
            if query == "flaky" and self.calls[query] == 1:
                raise ValueError("retry me")
            return query.upper()

    delegate = Delegate()
    cached = CachedQueryRewriter(delegate)

    assert cached.rewrite("stable") == "STABLE"
    assert cached.rewrite("stable") == "STABLE"
    with pytest.raises(ValueError, match="retry me"):
        cached.rewrite("flaky")
    assert cached.rewrite("flaky") == "FLAKY"
    assert delegate.calls == {"stable": 1, "flaky": 2}
    assert cached.delegate_counters.calls == 3
    assert cached.delegate_counters.successes == 2
    assert cached.delegate_counters.failures == 1
    assert cached.delegate_counters.latency_seconds >= 0.0


def test_recording_llm_counts_only_real_complete_calls_in_real_rewriter() -> None:
    from app.retrieval.query_rewriter import LlmQueryRewriter
    from stage2b_common import RecordingLlmClient

    class FailingLlm:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("provider failed")

    recording = RecordingLlmClient(FailingLlm())
    rewriter = LlmQueryRewriter(recording)

    assert rewriter.rewrite("alert API") == "alert API"
    assert recording.provider_counters.calls == 0
    assert rewriter.rewrite("告警 API 在哪里？") == "告警 API 在哪里？"
    assert recording.provider_counters.calls == 1
    assert recording.provider_counters.failures == 1


def test_recording_openai_client_counts_each_embedding_batch_request() -> None:
    from types import SimpleNamespace

    from app.retrieval.embedding_service import OpenAICompatibleEmbeddingProvider
    from stage2b_common import RecordingOpenAIClient

    class EmbeddingsEndpoint:
        def __init__(self) -> None:
            self.offset = 0

        def create(self, **request: object) -> object:
            inputs = request["input"]
            assert isinstance(inputs, list)
            data = [
                SimpleNamespace(index=index, embedding=[float(self.offset + index)])
                for index in range(len(inputs))
            ]
            self.offset += len(inputs)
            return SimpleNamespace(data=data)

    raw_client = SimpleNamespace(embeddings=EmbeddingsEndpoint())
    recording = RecordingOpenAIClient(raw_client)
    provider = OpenAICompatibleEmbeddingProvider(
        "embedding-3", "test-key", client=recording
    )

    vectors = provider.embed_documents([f"text-{index}" for index in range(130)])

    assert len(vectors) == 130
    assert recording.provider_counters.calls == 3
    assert recording.provider_counters.successes == 3
    assert recording.provider_counters.failures == 0


def test_recording_llm_write_ahead_attempt_begins_before_delegate() -> None:
    from stage2b_common import RecordingLlmClient

    events: list[object] = []

    class Counters:
        def begin_attempt(self) -> str:
            events.append("started")
            return "attempt-1"

        def finish_attempt(self, attempt_id: str, outcome: str, latency: float) -> None:
            events.append((attempt_id, outcome))

    class Delegate:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            assert events == ["started"]
            events.append("delegate")
            return "ok"

    assert RecordingLlmClient(Delegate(), Counters()).complete("s", "u") == "ok"
    assert events == ["started", "delegate", ("attempt-1", "success")]


def test_recording_embedding_write_ahead_attempt_begins_before_delegate() -> None:
    from types import SimpleNamespace

    from stage2b_common import RecordingOpenAIClient

    events: list[object] = []

    class Counters:
        def begin_attempt(self) -> str:
            events.append("started")
            return "attempt-1"

        def finish_attempt(self, attempt_id: str, outcome: str, latency: float) -> None:
            events.append((attempt_id, outcome))

    class Endpoint:
        def create(self, **request: object) -> object:
            assert events == ["started"]
            events.append("delegate")
            return "response"

    client = RecordingOpenAIClient(SimpleNamespace(embeddings=Endpoint()), Counters())
    assert client.embeddings.create(model="m", input=["q"]) == "response"
    assert events == ["started", "delegate", ("attempt-1", "success")]


def test_checkpoint_writer_resumes_by_question_variant_and_run_index(
    tmp_path: Path,
) -> None:
    from stage2b_common import JsonlCheckpointWriter

    output = tmp_path / "raw.jsonl"
    first = {"question_id": "q1", "variant": "b5", "run_index": 0}
    second = {"question_id": "q1", "variant": "b5", "run_index": 1}

    with JsonlCheckpointWriter(output) as writer:
        assert writer.append(first) is True
        assert writer.append(first) is False
        assert writer.append(second) is True

    with JsonlCheckpointWriter(output) as resumed:
        assert resumed.is_completed("q1", "b5", 0)
        assert resumed.is_completed("q1", "b5", 1)
        assert not resumed.is_completed("q1", "b4", 0)

    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert records == [first, second]


def test_checkpoint_writer_flushes_and_fsyncs_each_new_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stage2b_common import JsonlCheckpointWriter

    fsync_calls: list[int] = []
    monkeypatch.setattr(os, "fsync", fsync_calls.append)

    with JsonlCheckpointWriter(tmp_path / "raw.jsonl") as writer:
        writer.append({"question_id": "q1", "variant": "b2", "run_index": 0})

    assert len(fsync_calls) == 1


def test_checkpoint_writer_quarantines_only_an_unterminated_torn_final_line(
    tmp_path: Path,
) -> None:
    from stage2b_common import JsonlCheckpointWriter

    output = tmp_path / "raw.jsonl"
    valid = {"question_id": "q1", "variant": "b5", "run_index": 0}
    output.write_bytes(
        (json.dumps(valid) + "\n").encode() + b'{"question_id":"q2"'
    )

    with JsonlCheckpointWriter(output) as writer:
        assert writer.is_completed("q1", "b5", 0)
        assert writer.quarantine_path.read_bytes() == b'{"question_id":"q2"'
        assert writer.append(
            {"question_id": "q2", "variant": "b5", "run_index": 0}
        )

    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert [record["question_id"] for record in records] == ["q1", "q2"]


def test_torn_recovery_durably_quarantines_then_truncates_prefix_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stage2b_common import JsonlCheckpointWriter

    output = tmp_path / "raw.jsonl"
    valid_prefix = (
        json.dumps(
            {"question_id": "中文", "variant": "b5", "run_index": 0},
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    torn = b'{"question_id":"torn"'
    output.write_bytes(valid_prefix + torn)

    original_open = Path.open
    checkpoint_modes: list[str] = []
    seek_offsets: list[int] = []
    truncate_calls: list[object] = []
    fsync_calls: list[int] = []

    class Probe:
        def __init__(self, stream: object) -> None:
            self.stream = stream

        def __enter__(self) -> "Probe":
            self.stream.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.stream.__exit__(*args)

        def seek(self, offset: int, *args: object) -> object:
            seek_offsets.append(offset)
            return self.stream.seek(offset, *args)

        def truncate(self, size: object = None) -> object:
            truncate_calls.append(size)
            return self.stream.truncate() if size is None else self.stream.truncate(size)

        def __getattr__(self, name: str) -> object:
            return getattr(self.stream, name)

    def probing_open(path: Path, mode: str = "r", *args: object, **kwargs: object):
        stream = original_open(path, mode, *args, **kwargs)
        if path == output:
            checkpoint_modes.append(mode)
            if mode in {"r+b", "wb"}:
                return Probe(stream)
        return stream

    monkeypatch.setattr(Path, "open", probing_open)
    monkeypatch.setattr(os, "fsync", fsync_calls.append)

    JsonlCheckpointWriter(output)

    assert "r+b" in checkpoint_modes
    assert "wb" not in checkpoint_modes
    assert seek_offsets == [len(valid_prefix)]
    assert truncate_calls == [None]
    assert len(fsync_calls) == 2
    assert output.read_bytes() == valid_prefix
    assert Path(f"{output}.torn").read_bytes() == torn


def test_checkpoint_writer_rejects_malformed_middle_line(tmp_path: Path) -> None:
    from stage2b_common import JsonlCheckpointWriter

    output = tmp_path / "raw.jsonl"
    output.write_text(
        '{"question_id":"q1","variant":"b5","run_index":0}\n'
        "not-json\n"
        '{"question_id":"q2","variant":"b5","run_index":0}\n'
    )

    with pytest.raises(ValueError, match="invalid JSONL checkpoint"):
        JsonlCheckpointWriter(output)


@pytest.mark.parametrize("record", [None, [], "text"])
def test_checkpoint_writer_normalizes_non_object_json_error(
    tmp_path: Path, record: object
) -> None:
    from stage2b_common import JsonlCheckpointWriter

    output = tmp_path / "raw.jsonl"
    output.write_text(json.dumps(record) + "\n")

    with pytest.raises(ValueError, match="checkpoint JSON must be an object"):
        JsonlCheckpointWriter(output)


def test_checkpoint_writer_accepts_valid_final_json_without_newline(
    tmp_path: Path,
) -> None:
    from stage2b_common import JsonlCheckpointWriter

    output = tmp_path / "raw.jsonl"
    output.write_text('{"question_id":"q1","variant":"b5","run_index":0}')

    with JsonlCheckpointWriter(output) as writer:
        assert writer.is_completed("q1", "b5", 0)
        writer.append({"question_id": "q2", "variant": "b5", "run_index": 0})

    assert len(output.read_text().splitlines()) == 2


@pytest.mark.parametrize("run_index", [True, False, "1", 1.0, -1])
def test_checkpoint_key_requires_non_negative_plain_integer(run_index: object) -> None:
    from stage2b_common import checkpoint_key

    with pytest.raises(ValueError, match="non-negative integer run_index"):
        checkpoint_key(
            {"question_id": "q1", "variant": "b5", "run_index": run_index}
        )


def test_checkpoint_is_completed_uses_strict_run_index(tmp_path: Path) -> None:
    from stage2b_common import JsonlCheckpointWriter

    with JsonlCheckpointWriter(tmp_path / "raw.jsonl") as writer:
        with pytest.raises(ValueError, match="non-negative integer run_index"):
            writer.is_completed("q1", "b5", False)


def test_verify_sha256_accepts_match_and_refuses_mismatch(tmp_path: Path) -> None:
    from stage2b_common import ArtifactHashMismatchError, verify_sha256

    artifact = tmp_path / "dataset.jsonl"
    artifact.write_bytes(b"fixed evaluation data\n")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()

    assert verify_sha256(artifact, expected) == expected
    with pytest.raises(ArtifactHashMismatchError, match="SHA-256 mismatch"):
        verify_sha256(artifact, "0" * 64)


def test_run_metadata_serialization_removes_nested_secrets() -> None:
    from stage2b_common import RunMetadata

    metadata = RunMetadata(
        run_id="stage2b-001",
        dataset_path="evaluation/datasets/pilot-current.jsonl",
        dataset_sha256="a" * 64,
        providers={
            "embedding": {
                "model": "embedding-3",
                "base_url": "https://provider.invalid/v1",
                "api_key": "DO_NOT_SERIALIZE",
            },
            "llm": {
                "model": "mimo-v2.5",
                "headers": {"Authorization": "Bearer DO_NOT_SERIALIZE"},
                "access_token": "DO_NOT_SERIALIZE",
            },
        },
    )

    encoded = json.dumps(metadata.to_dict(), sort_keys=True)

    assert "embedding-3" in encoded
    assert "mimo-v2.5" in encoded
    assert "DO_NOT_SERIALIZE" not in encoded
    assert "api_key" not in encoded.lower()
    assert "authorization" not in encoded.lower()
    assert "access_token" not in encoded.lower()


def test_provider_metadata_can_be_sanitized_without_mutating_source() -> None:
    from stage2b_common import sanitize_provider_metadata

    source = {
        "model": "safe-model",
        "token": "secret",
        "nested": [{"client_secret": "secret", "dimension": 1024}],
    }

    sanitized = sanitize_provider_metadata(source)

    assert sanitized == {
        "model": "safe-model",
        "nested": [{"dimension": 1024}],
    }
    assert source["token"] == "secret"


def test_provider_metadata_removes_token_credentials_with_mixed_separators() -> None:
    from stage2b_common import sanitize_provider_metadata

    source = {
        "api key": "secret-space",
        "auth_token": "secret-auth",
        "id-token": "secret-id",
        "nested": {"refresh.token": "secret-refresh"},
        "token_count": 42,
        "max_tokens": 1024,
    }

    sanitized = sanitize_provider_metadata(source)

    assert sanitized == {
        "nested": {},
        "token_count": 42,
        "max_tokens": 1024,
    }
    assert "secret" not in json.dumps(sanitized)


def test_provider_metadata_removes_key_credentials_and_url_secrets() -> None:
    from stage2b_common import sanitize_provider_metadata

    source = {
        "secret_access_key": "secret-field",
        "secret key": "secret-field",
        "private-key": "secret-field",
        "base_url": (
            "https://user:password@example.test/v1?region=cn&api_key=secret-query"
            "#page=2&access_token=secret-fragment"
        ),
    }

    sanitized = sanitize_provider_metadata(source)

    assert sanitized == {
        "base_url": "https://example.test/v1?region=cn#page=2",
    }
    assert "secret" not in json.dumps(sanitized)


def test_provider_metadata_removes_camel_case_tokens_but_keeps_counts() -> None:
    from stage2b_common import sanitize_provider_metadata

    source = {
        "authToken": "secret-auth",
        "accessToken": "secret-access",
        "refreshToken": "secret-refresh",
        "idToken": "secret-id",
        "apiToken": "secret-api",
        "tokenCount": 10,
        "maxTokens": 20,
        "token_count": 30,
        "max_tokens": 40,
    }

    assert sanitize_provider_metadata(source) == {
        "tokenCount": 10,
        "maxTokens": 20,
        "token_count": 30,
        "max_tokens": 40,
    }


def test_provider_metadata_removes_subscription_keys_and_url_key_parameter() -> None:
    from stage2b_common import sanitize_provider_metadata

    source = {
        "subscription-key": "secret-dash",
        "subscription_key": "secret-underscore",
        "subscriptionKey": "secret-camel",
        "base_url": "https://example.test/v1?region=cn&key=secret-url&page=2",
    }

    assert sanitize_provider_metadata(source) == {
        "base_url": "https://example.test/v1?region=cn&page=2",
    }
