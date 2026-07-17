"""Stage 2B real-service retrieval and GraphRAG benchmark runner.

The runner reads the already-scanned, isolated Pilot SQLite database and builds
vectors in a dedicated local Qdrant directory.  Product retrieval components
are composed directly; ablation-only fusion lives here so benchmark switches
cannot change application behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
EVALUATION_SCRIPTS_DIR = ROOT / "evaluation" / "scripts"
if str(EVALUATION_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_SCRIPTS_DIR))

from stable_entity_key import compute_stable_key  # noqa: E402

from stage2b_common import (  # noqa: E402
    CachedEmbeddingService,
    JsonlCheckpointWriter,
    RecordingLlmClient,
    RecordingOpenAIClient,
    checkpoint_key,
    sanitize_error_message,
    sanitize_provider_metadata,
    sha256_file,
    verify_sha256,
)


TOP_K = 10
CANDIDATE_LIMIT = 20
FROZEN_RETRIEVAL_OUTPUT = ROOT / "evaluation/results/raw/stage2b_retrieval.jsonl"
FROZEN_RETRIEVAL_METADATA = ROOT / "evaluation/results/raw/stage2b_retrieval.metadata.json"
FROZEN_PROVIDER_LEDGERS = ROOT / "evaluation/runtime/pilot/stage2b_provider_ledgers"


class DurableCallCounters:
    """CallCounters-compatible provider accounting backed by an event ledger."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Materialize even a zero-call ledger so downstream provenance can
        # hash it. Append mode creates missing files without truncating a
        # ledger from an interrupted or resumed run.
        with self.path.open("ab") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        self.calls = 0
        self.successes = 0
        self.failures = 0
        self.latency_seconds = 0.0
        self._attempts: dict[str, bool] = {}
        if self.path.exists():
            content = self.path.read_bytes()
            lines = content.splitlines(keepends=True)
            torn_final = bool(content) and not content.endswith((b"\n", b"\r"))
            quarantined = False
            for index, raw in enumerate(lines):
                line_number = index + 1
                line = raw.rstrip(b"\r\n")
                if not line.strip():
                    continue
                try:
                    event = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    if index == len(lines) - 1 and torn_final:
                        with Path(f"{self.path}.torn").open("wb") as quarantine:
                            quarantine.write(line)
                            quarantine.flush()
                            os.fsync(quarantine.fileno())
                        valid = b"".join(lines[:-1])
                        with self.path.open("r+b") as stream:
                            stream.seek(len(valid))
                            stream.truncate()
                            stream.flush()
                            os.fsync(stream.fileno())
                        quarantined = True
                        break
                    raise ValueError(
                        f"invalid provider event ledger at {self.path}:{line_number}"
                    ) from error
                try:
                    if not isinstance(event, Mapping):
                        raise TypeError("provider event must be an object")
                    self._replay_event(event)
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"invalid provider event ledger at {self.path}:{line_number}"
                    ) from error
            if torn_final and not quarantined:
                with self.path.open("ab") as stream:
                    stream.write(b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())

    def _apply(self, outcome: str, latency_seconds: float) -> None:
        if outcome not in {"success", "failure"} or latency_seconds < 0:
            raise ValueError("provider event must have a valid outcome and latency")
        self.calls += 1
        self.successes += int(outcome == "success")
        self.failures += int(outcome == "failure")
        self.latency_seconds += latency_seconds

    def _replay_event(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("event")
        if event_type is None:
            self._apply(str(event["outcome"]), float(event["latency_seconds"]))
            return
        attempt_id = str(event["attempt_id"])
        if event_type == "started":
            if attempt_id in self._attempts:
                raise ValueError("duplicate provider attempt start")
            self._attempts[attempt_id] = True
            self.calls += 1
            return
        if event_type == "finished":
            if attempt_id not in self._attempts:
                raise ValueError("unknown or duplicate provider attempt finish")
            outcome = str(event["outcome"])
            latency = float(event["latency_seconds"])
            if outcome not in {"success", "failure"} or latency < 0:
                raise ValueError("provider finish must have a valid outcome and latency")
            self.successes += int(outcome == "success")
            self.failures += int(outcome == "failure")
            self.latency_seconds += latency
            del self._attempts[attempt_id]
            return
        raise ValueError("unknown provider ledger event")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_event(self, event: Mapping[str, Any]) -> None:
        encoded = json.dumps(dict(event), separators=(",", ":"))
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def begin_attempt(self) -> str:
        attempt_id = uuid.uuid4().hex
        event = {
            "event": "started",
            "attempt_id": attempt_id,
            "timestamp": self._timestamp(),
        }
        self._append_event(event)
        self._replay_event(event)
        return attempt_id

    def finish_attempt(
        self,
        attempt_id: str,
        outcome: str,
        latency_seconds: float,
    ) -> None:
        if attempt_id not in self._attempts:
            raise ValueError("unknown or duplicate provider attempt finish")
        event = {
            "event": "finished",
            "attempt_id": attempt_id,
            "outcome": outcome,
            "latency_seconds": latency_seconds,
            "timestamp": self._timestamp(),
        }
        self._append_event(event)
        self._replay_event(event)

    @property
    def pending(self) -> int:
        return len(self._attempts)

    @property
    def unconfirmed(self) -> int:
        return self.pending

    def _record(self, outcome: str, latency_seconds: float) -> None:
        event = json.dumps(
            {"outcome": outcome, "latency_seconds": latency_seconds},
            separators=(",", ":"),
        )
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(event + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._apply(outcome, latency_seconds)

    def record_success(self, latency_seconds: float) -> None:
        self._record("success", latency_seconds)

    def record_failure(self, latency_seconds: float) -> None:
        self._record("failure", latency_seconds)

    def to_dict(self) -> dict[str, int | float]:
        return {
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "latency_seconds": self.latency_seconds,
            "pending": self.pending,
            "unconfirmed": self.unconfirmed,
        }


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def resolve_run_id(
    previous: Mapping[str, Any] | None,
    explicit: str | None,
    dataset_sha256: str,
    repo_commit: str,
    db_sha256: str = "",
    snapshot_sha256: str = "",
    config_fingerprint: str = "",
) -> str:
    """Resolve a stable, filesystem-safe identity before provider composition."""
    if previous:
        if previous.get("dataset_sha256") != dataset_sha256:
            raise ValueError("existing metadata dataset SHA does not match requested dataset")
        if previous.get("repo_commit") != repo_commit:
            raise ValueError("existing metadata repository commit does not match requested commit")
        if db_sha256 and previous.get("db_sha256") != db_sha256:
            raise ValueError("existing metadata database SHA does not match requested database")
        if snapshot_sha256 and previous.get("snapshot_sha256") != snapshot_sha256:
            raise ValueError("existing metadata snapshot SHA does not match requested snapshot")
        if config_fingerprint and previous.get("config_fingerprint") != config_fingerprint:
            raise ValueError("existing metadata config fingerprint does not match requested config")
        run_id = str(previous["run_id"])
        if explicit and explicit != run_id:
            raise ValueError("explicit run_id conflicts with existing metadata")
    elif explicit:
        run_id = explicit
    else:
        identity = hashlib.sha256(
            f"{dataset_sha256}:{repo_commit}:{db_sha256}:{snapshot_sha256}:{config_fingerprint}".encode("ascii")
        ).hexdigest()[:16]
        run_id = f"stage2b-{identity}"
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id may contain only letters, digits, dot, underscore, and dash")
    return run_id


@dataclass(frozen=True)
class Variant:
    mode: str = "hybrid"
    rewrite: bool = True
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    fusion: str = "weighted"
    graph_depth: int | None = None


VARIANTS: dict[str, Variant] = {
    "B2": Variant(mode="vector"),
    "B3": Variant(),
    "B4": Variant(graph_depth=2),
    "A1": Variant(rewrite=False),
    "A2": Variant(vector_weight=0.5, keyword_weight=0.5),
    "A3": Variant(vector_weight=0.3, keyword_weight=0.7),
    "A4": Variant(fusion="rrf"),
    "A5": Variant(graph_depth=0),
    "A6": Variant(graph_depth=1),
}

# Explicit opt-in development sweep.  These variants deliberately remain
# outside VARIANTS so the frozen nine-variant Stage 2B default is unchanged.
WEIGHT_SWEEP_VARIANTS: dict[str, Variant] = {
    "W60": Variant(vector_weight=0.60, keyword_weight=0.40),
    "W65": Variant(vector_weight=0.65, keyword_weight=0.35),
    "W70": Variant(vector_weight=0.70, keyword_weight=0.30),
    "W75": Variant(vector_weight=0.75, keyword_weight=0.25),
    "W80": Variant(vector_weight=0.80, keyword_weight=0.20),
    "W85": Variant(vector_weight=0.85, keyword_weight=0.15),
    "W90": Variant(vector_weight=0.90, keyword_weight=0.10),
    "W95": Variant(vector_weight=0.95, keyword_weight=0.05),
}


def resolve_variant(name: str) -> Variant:
    """Resolve a frozen benchmark or explicitly selected weight-sweep variant."""
    if name in VARIANTS:
        return VARIANTS[name]
    return WEIGHT_SWEEP_VARIANTS[name]


def variant_config(variant: Variant) -> dict[str, Any]:
    """Serialize the effective variant settings for metadata and raw records."""
    return {
        "mode": variant.mode,
        "rewrite": variant.rewrite,
        "vector_weight": variant.vector_weight,
        "keyword_weight": variant.keyword_weight,
        "fusion": variant.fusion,
        "graph_depth": variant.graph_depth,
    }


def parse_variants(value: str) -> tuple[str, ...]:
    """Parse an explicit, ordered subset of benchmark variants."""
    names = value.split(",")
    if not names or any(not name for name in names):
        raise argparse.ArgumentTypeError("variants must be a non-empty comma-separated list")
    allowed = VARIANTS.keys() | WEIGHT_SWEEP_VARIANTS.keys()
    unknown = [name for name in names if name not in allowed]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown retrieval variant: {unknown[0]}")
    if len(set(names)) != len(names):
        raise argparse.ArgumentTypeError("retrieval variants must not contain duplicates")
    return tuple(names)


def validate_selected_artifact_paths(
    variants: Sequence[str], output: Path, metadata: Path, ledger_dir: Path
) -> None:
    """Keep focused reruns separate from the frozen full Stage 2B artifacts."""
    if tuple(variants) == tuple(VARIANTS):
        return
    if (
        output.resolve() == FROZEN_RETRIEVAL_OUTPUT.resolve()
        or metadata.resolve() == FROZEN_RETRIEVAL_METADATA.resolve()
        or ledger_dir.resolve() == FROZEN_PROVIDER_LEDGERS.resolve()
    ):
        raise ValueError(
            "selected-variant runs require separate --output, --metadata, and --ledger-dir paths"
        )


@dataclass
class RetrievalRuntime:
    project_id: int
    entity_keys: Mapping[int, str]
    embeddings: Any
    vector_store: Any
    keyword_search: Any
    rewriter: Any
    graph_retriever: Any
    graph_query: Any
    graph_capture: Any
    identity: Mapping[str, str] = None  # type: ignore[assignment]
    hybrid_search: Any | None = None
    _rewrites: dict[str, str] | None = None
    _vectors: dict[str, tuple[float, ...]] | None = None

    def __post_init__(self) -> None:
        self.identity = {} if self.identity is None else self.identity
        self._rewrites = {} if self._rewrites is None else self._rewrites
        self._vectors = {} if self._vectors is None else self._vectors

    def effective_query(self, query: str, rewrite_query: bool) -> str:
        if not rewrite_query:
            return query
        assert self._rewrites is not None
        if query not in self._rewrites:
            self._rewrites[query] = self.rewriter.rewrite(query)
        return self._rewrites[query]

    def query_vector(self, query: str) -> list[float]:
        assert self._vectors is not None
        if query not in self._vectors:
            self._vectors[query] = tuple(self.embeddings.embed_query(query))
        return list(self._vectors[query])


class SourceRetrievalError(RuntimeError):
    def __init__(self, source: str, cause: Exception) -> None:
        super().__init__(sanitize_error_message(cause))
        self.source = source
        self.cause = cause


class CapturingGraphTraversal:
    """Transparent GraphTraversal wrapper retaining successful source results."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.results: list[Any] = []

    def reset(self) -> None:
        self.results.clear()

    def traverse(
        self,
        project_id: int,
        entity_id: int,
        *,
        max_depth: int,
        relation_types: tuple[str, ...] | None,
    ) -> Any:
        result = self.delegate.traverse(
            project_id,
            entity_id,
            max_depth=max_depth,
            relation_types=relation_types,
        )
        self.results.append(result)
        return result

    def merged(self) -> Any:
        from app.graph.types import GraphResult

        nodes: dict[int, Any] = {}
        edges: dict[int, Any] = {}
        for result in self.results:
            for node in result.nodes:
                nodes.setdefault(node.entity_id, node)
            for edge in result.edges:
                edges.setdefault(edge.relation_id, edge)
        return GraphResult(
            nodes=tuple(sorted(nodes.values(), key=lambda node: node.entity_id)),
            edges=tuple(
                sorted(
                    edges.values(),
                    key=lambda edge: (
                        edge.source_id,
                        edge.target_id,
                        edge.relation_type,
                        edge.relation_id,
                    ),
                )
            ),
        )


class DurableRewriteCache:
    """Persistent product-equivalent query rewriting with observable fallback."""

    def __init__(self, llm: Any, path: Path) -> None:
        self.llm = llm
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            content = self.path.read_bytes()
            lines = content.splitlines(keepends=True)
            torn_final = bool(content) and not content.endswith((b"\n", b"\r"))
            quarantined = False
            for index, raw in enumerate(lines):
                line_number = index + 1
                line = raw.rstrip(b"\r\n")
                try:
                    event = json.loads(line.decode("utf-8"))
                    self._events[str(event["original_query"])] = event
                except (UnicodeDecodeError, KeyError, TypeError, json.JSONDecodeError) as error:
                    if index == len(lines) - 1 and torn_final:
                        with Path(f"{self.path}.torn").open("wb") as quarantine:
                            quarantine.write(line)
                            quarantine.flush()
                            os.fsync(quarantine.fileno())
                        valid = b"".join(lines[:-1])
                        with self.path.open("r+b") as stream:
                            stream.seek(len(valid))
                            stream.truncate()
                            stream.flush()
                            os.fsync(stream.fileno())
                        quarantined = True
                        break
                    raise ValueError(
                        f"invalid rewrite cache at {self.path}:{line_number}"
                    ) from error
            if torn_final and not quarantined:
                with self.path.open("ab") as stream:
                    stream.write(b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())

    def rewrite(self, query: str) -> str:
        from app.retrieval.query_rewriter import REWRITE_PROMPT, contains_cjk

        original = query.strip()
        if original in self._events:
            return str(self._events[original]["effective_query"])
        started = time.perf_counter()
        degraded = False
        error_record = None
        effective = original
        if contains_cjk(original):
            try:
                effective = " ".join(self.llm.complete(REWRITE_PROMPT, original).split()) or original
            except Exception as error:
                degraded = True
                error_record = {
                    "type": type(error).__name__,
                    "message": sanitize_error_message(error),
                }
        latency = time.perf_counter() - started
        event = {
            "original_query": original,
            "effective_query": effective,
            "rewrite_degraded": degraded,
            "rewrite_error": error_record,
            "rewrite_latency_seconds": latency,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._events[original] = event
        return effective

    def details(self, query: str) -> dict[str, Any]:
        return dict(self._events[query.strip()])

    @property
    def entry_count(self) -> int:
        return len(self._events)


def process_counter_metadata(
    embeddings: Any,
    rewrite_cache: DurableRewriteCache,
) -> dict[str, Any]:
    """Return process-local diagnostics without assuming rewrite delegates."""
    return {
        "embedding_service": embeddings.delegate_counters.to_dict(),
        "rewrite_cache_entries": rewrite_cache.entry_count,
    }


def provider_ledger_summary(counters: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """Summarize unfinished durable attempts under the selected-run contract.

    Retrieval ledgers define an orphan as an attempt with no durable finished
    event.  DurableCallCounters exposes that state as ``unconfirmed``.
    """
    return {
        name: {
            "pending": int(counter.pending),
            "unconfirmed": int(counter.unconfirmed),
            "orphan": int(counter.unconfirmed),
        }
        for name, counter in counters.items()
    }


def _positive_max(hits: Sequence[Any]) -> float:
    return max((float(item.score) for item in hits if item.score > 0), default=0.0)


def _normalized(score: float, maximum: float) -> float:
    return score / maximum if score > 0 and maximum > 0 else 0.0


def weighted_fusion(
    vector_hits: Sequence[Any],
    keyword_hits: Sequence[Any],
    *,
    vector_weight: float,
    keyword_weight: float,
    limit: int,
) -> list[Any]:
    """Fuse independently normalized source scores without mutating hits."""
    vector_max = _positive_max(vector_hits)
    keyword_max = _positive_max(keyword_hits)
    originals: dict[int, Any] = {}
    scores: dict[int, float] = {}
    for item in vector_hits:
        originals.setdefault(item.entity_id, item)
        scores[item.entity_id] = vector_weight * _normalized(item.score, vector_max)
    for item in keyword_hits:
        originals.setdefault(item.entity_id, item)
        scores[item.entity_id] = scores.get(item.entity_id, 0.0) + (
            keyword_weight * _normalized(item.score, keyword_max)
        )
    source = f"hybrid_{vector_weight:g}v_{keyword_weight:g}k"
    fused = [replace(originals[key], score=score, source=source) for key, score in scores.items()]
    return sorted(fused, key=lambda item: (-item.score, item.entity_id))[:limit]


def reciprocal_rank_fusion(
    vector_hits: Sequence[Any],
    keyword_hits: Sequence[Any],
    *,
    limit: int,
    rank_constant: int = 60,
) -> list[Any]:
    originals: dict[int, Any] = {}
    scores: dict[int, float] = {}
    for ranked in (vector_hits, keyword_hits):
        for rank, item in enumerate(ranked, start=1):
            originals.setdefault(item.entity_id, item)
            scores[item.entity_id] = scores.get(item.entity_id, 0.0) + 1 / (rank_constant + rank)
    fused = [replace(originals[key], score=score, source="rrf") for key, score in scores.items()]
    return sorted(fused, key=lambda item: (-item.score, item.entity_id))[:limit]


def serialize_hit(item: Any, entity_keys: Mapping[int, str]) -> dict[str, Any]:
    return {
        "runtime_entity_id": item.entity_id,
        "stable_entity_key": entity_keys.get(item.entity_id),
        "entity_type": item.entity_type,
        "name": item.name,
        "qualified_name": item.qualified_name,
        "file_path": item.file_path,
        "start_line": item.start_line,
        "end_line": item.end_line,
        "score": item.score,
        "source": item.source,
        "metadata": item.metadata,
        "uncertainties": list(item.uncertainties),
    }


def _serialize_graph_result(item: Any, entity_keys: Mapping[int, str]) -> dict[str, Any]:
    return {
        "runtime_entity_id": item.entity_id,
        "stable_entity_key": entity_keys.get(item.entity_id),
        "entity_type": item.entity_type,
        "name": item.name,
        "qualified_name": item.qualified_name,
        "file_path": item.file_path,
        "start_line": item.start_line,
        "end_line": item.end_line,
        "retrieval_score": item.retrieval_score,
        "graph_depth": item.graph_depth,
        "relation_reason": item.relation_reason,
        "seed_runtime_entity_id": item.seed_entity_id,
        "seed_stable_entity_key": entity_keys.get(item.seed_entity_id),
        "metadata": item.metadata,
        "uncertainties": list(item.uncertainties),
    }


def _serialize_graph(graph: Any, entity_keys: Mapping[int, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [
        {
            "runtime_entity_id": node.entity_id,
            "stable_entity_key": entity_keys.get(node.entity_id),
            "entity_type": node.entity_type,
            "label": node.label,
            "qualified_name": node.qualified_name,
            "file_path": node.file_path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "metadata": node.metadata,
        }
        for node in graph.nodes
    ]
    edges = [
        {
            "runtime_relation_id": edge.relation_id,
            "source_runtime_id": edge.source_id,
            "target_runtime_id": edge.target_id,
            "source_stable_entity_key": entity_keys.get(edge.source_id),
            "target_stable_entity_key": entity_keys.get(edge.target_id),
            "relation_type": edge.relation_type,
            "confidence": edge.confidence,
            "metadata": edge.metadata,
        }
        for edge in graph.edges
    ]
    return nodes, edges


def _source_hits(runtime: RetrievalRuntime, effective_query: str) -> tuple[list[Any], list[Any]]:
    try:
        vector = runtime.vector_store.search(
            runtime.project_id, runtime.query_vector(effective_query), CANDIDATE_LIMIT
        )
    except Exception as error:
        raise SourceRetrievalError("vector", error) from error
    try:
        keyword = runtime.keyword_search.search(runtime.project_id, effective_query, CANDIDATE_LIMIT)
    except Exception as error:
        raise SourceRetrievalError("keyword", error) from error
    return vector, keyword


def _stable_hit_key(item: Any, entity_keys: Mapping[int, str]) -> str:
    key = entity_keys.get(item.entity_id)
    if not key:
        raise ValueError(f"missing stable entity key for runtime entity {item.entity_id}")
    return key


def _sorted_vector_hits(
    hits: Sequence[Any], entity_keys: Mapping[int, str]
) -> list[Any]:
    return sorted(hits, key=lambda item: (-item.score, _stable_hit_key(item, entity_keys)))


def _branch_diagnostics(
    vector_hits: Sequence[Any],
    keyword_hits: Sequence[Any],
    fused_hits: Sequence[Any],
    entity_keys: Mapping[int, str],
) -> dict[str, Any]:
    vector_keys = [
        _stable_hit_key(item, entity_keys)
        for item in _sorted_vector_hits(vector_hits, entity_keys)
    ]
    keyword_keys = [_stable_hit_key(item, entity_keys) for item in keyword_hits]
    fused_keys = [_stable_hit_key(item, entity_keys) for item in fused_hits]
    vector_set = set(vector_keys)
    keyword_set = set(keyword_keys)
    return {
        "vector_candidate_count": len(vector_hits),
        "keyword_candidate_count": len(keyword_hits),
        "overlap_count": len(vector_set & keyword_set),
        "keyword_only_count": len(keyword_set - vector_set),
        "top10_changed_from_vector": fused_keys[:TOP_K] != vector_keys[:TOP_K],
    }


def _product_source_hits(
    runtime: RetrievalRuntime, effective_query: str
) -> tuple[list[Any], list[Any], str | None]:
    """Fetch each product source once while retaining product fallback behavior."""
    from app.errors import DomainError
    from app.retrieval.hybrid_search import (
        KEYWORD_FALLBACK_UNCERTAINTY,
        VECTOR_FALLBACK_UNCERTAINTY,
    )

    vector_error: Exception | None = None
    keyword_error: Exception | None = None
    try:
        vector = runtime.vector_store.search(
            runtime.project_id, runtime.query_vector(effective_query), CANDIDATE_LIMIT
        )
    except Exception as error:
        vector = []
        vector_error = error
    try:
        keyword = runtime.keyword_search.search(
            runtime.project_id, effective_query, CANDIDATE_LIMIT
        )
    except DomainError:
        raise
    except Exception as error:
        keyword = []
        keyword_error = error
    if vector_error and keyword_error:
        raise SourceRetrievalError("hybrid", vector_error) from vector_error
    if vector_error:
        keyword = [
            replace(
                item,
                source="keyword_fallback",
                uncertainties=(*item.uncertainties, VECTOR_FALLBACK_UNCERTAINTY),
            )
            for item in keyword
        ]
        return vector, keyword, "keyword"
    if keyword_error:
        vector = [
            replace(
                item,
                source="vector_fallback",
                uncertainties=(*item.uncertainties, KEYWORD_FALLBACK_UNCERTAINTY),
            )
            for item in vector
        ]
        return vector, keyword, "vector"
    return vector, keyword, None


def _direct_hits(
    runtime: RetrievalRuntime, effective_query: str, variant: Variant
) -> tuple[list[Any], dict[str, Any] | None]:
    if variant.mode == "vector":
        try:
            hits = runtime.vector_store.search(
                runtime.project_id, runtime.query_vector(effective_query), CANDIDATE_LIMIT
            )
            return _sorted_vector_hits(hits, runtime.entity_keys)[:TOP_K], None
        except Exception as error:
            raise SourceRetrievalError("vector", error) from error
    fallback: str | None = None
    if runtime.hybrid_search is not None:
        vector, keyword, fallback = _product_source_hits(runtime, effective_query)
    else:
        vector, keyword = _source_hits(runtime, effective_query)
    if fallback == "keyword":
        hits = keyword[:TOP_K]
    elif fallback == "vector":
        hits = vector[:TOP_K]
    elif variant.fusion == "rrf":
        hits = reciprocal_rank_fusion(vector, keyword, limit=TOP_K)
    else:
        hits = weighted_fusion(
            vector,
            keyword,
            vector_weight=variant.vector_weight,
            keyword_weight=variant.keyword_weight,
            limit=TOP_K,
        )
    return hits, _branch_diagnostics(vector, keyword, hits, runtime.entity_keys)


def evaluate_case(case: Mapping[str, Any], variant_name: str, runtime: RetrievalRuntime) -> dict[str, Any]:
    variant = resolve_variant(variant_name)
    query = str(case["question"])
    logical_started = time.perf_counter()
    effective = runtime.effective_query(query, variant.rewrite)
    rewrite_details = (
        runtime.rewriter.details(query)
        if variant.rewrite and hasattr(runtime.rewriter, "details")
        else {
            "rewrite_latency_seconds": 0.0,
            "rewrite_degraded": False,
            "rewrite_error": None,
        }
    )
    rewrite_latency = float(rewrite_details.get("rewrite_latency_seconds", 0.0))
    retrieval_started = time.perf_counter()
    record: dict[str, Any] = {
        "question_id": str(case["question_id"]),
        "variant": variant_name,
        "variant_config": variant_config(variant),
        "run_index": 0,
        "query": query,
        "effective_query": effective,
        "rewrite_latency_seconds": rewrite_latency,
        "rewrite_degraded": bool(rewrite_details.get("rewrite_degraded", False)),
        "rewrite_error": rewrite_details.get("rewrite_error"),
        "status": "ok",
        "hits": [],
        "graph_results": [],
        "graph_nodes": [],
        "graph_edges": [],
        **dict(runtime.identity),
    }
    try:
        if variant.graph_depth is None:
            hits, diagnostics = _direct_hits(runtime, effective, variant)
            record["hits"] = [serialize_hit(item, runtime.entity_keys) for item in hits]
            if diagnostics is not None:
                record["branch_diagnostics"] = diagnostics
        else:
            runtime.graph_capture.reset()
            expanded = runtime.graph_retriever.retrieve(
                runtime.project_id, effective, limit=TOP_K, max_depth=variant.graph_depth
            )
            direct = [item for item in expanded if item.graph_depth == 0]
            record["hits"] = [
                {
                    "runtime_entity_id": item.entity_id,
                    "stable_entity_key": runtime.entity_keys.get(item.entity_id),
                    "entity_type": item.entity_type,
                    "name": item.name,
                    "qualified_name": item.qualified_name,
                    "file_path": item.file_path,
                    "start_line": item.start_line,
                    "end_line": item.end_line,
                    "score": item.retrieval_score,
                    "source": "hybrid",
                    "metadata": item.metadata,
                    "uncertainties": list(item.uncertainties),
                }
                for item in direct[:TOP_K]
            ]
            record["graph_results"] = [
                _serialize_graph_result(item, runtime.entity_keys) for item in expanded
            ]
            graph = runtime.graph_capture.merged()
            record["graph_nodes"], record["graph_edges"] = _serialize_graph(graph, runtime.entity_keys)
    except Exception as error:
        cause = error.cause if isinstance(error, SourceRetrievalError) else error
        record["status"] = "error"
        record["error"] = {
            "source": error.source if isinstance(error, SourceRetrievalError) else "retrieval",
            "type": type(cause).__name__,
            "message": sanitize_error_message(cause),
        }
        record["hits"] = []
        record["graph_results"] = []
        record["graph_nodes"] = []
        record["graph_edges"] = []
    record["retrieval_latency_seconds"] = time.perf_counter() - retrieval_started
    record["latency_seconds"] = rewrite_latency + record["retrieval_latency_seconds"]
    record["wall_latency_seconds"] = time.perf_counter() - logical_started
    return record


def run_questions(
    questions: Sequence[Mapping[str, Any]],
    runtime: RetrievalRuntime,
    output_path: Path,
    *,
    variants: Sequence[str] = tuple(VARIANTS),
) -> int:
    validate_raw_identity(output_path, runtime.identity)
    written = 0
    with JsonlCheckpointWriter(output_path) as checkpoint:
        for case in questions:
            for variant in variants:
                if checkpoint.is_completed(str(case["question_id"]), variant, 0):
                    continue
                written += int(checkpoint.append(evaluate_case(case, variant, runtime)))
    return written


def _atomic_write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(
                json.dumps(dict(record), ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def run_smoke_gate(
    questions: Sequence[Mapping[str, Any]],
    runtime: RetrievalRuntime,
    canonical_output: Path,
    *,
    variants: Sequence[str] = ("B2", "B3", "B4"),
) -> list[dict[str, Any]]:
    """Isolate smoke records; promote only an entirely successful probe."""
    temporary = canonical_output.with_name(
        f".{canonical_output.name}.smoke-{uuid.uuid4().hex}.tmp.jsonl"
    )
    run_questions(questions, runtime, temporary, variants=variants)
    validate_raw_identity(temporary, runtime.identity)
    smoke_records = [
        json.loads(line)
        for line in temporary.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failed = [record for record in smoke_records if record.get("status") != "ok"]
    if failed:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        failed_path = canonical_output.with_name(
            f"{canonical_output.stem}.smoke-failed-{stamp}{canonical_output.suffix}"
        )
        os.replace(temporary, failed_path)
        raise RuntimeError(
            f"smoke retrieval failed for {len(failed)} record(s); preserved at {failed_path}"
        )

    validate_raw_identity(canonical_output, runtime.identity)
    existing = []
    if canonical_output.exists():
        existing = [
            json.loads(line)
            for line in canonical_output.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    merged = list(existing)
    keys = {checkpoint_key(record) for record in existing}
    for record in smoke_records:
        key = checkpoint_key(record)
        if key not in keys:
            merged.append(record)
            keys.add(key)
    _atomic_write_jsonl(canonical_output, merged)
    temporary.unlink(missing_ok=True)
    return smoke_records


_RAW_IDENTITY_FIELDS = (
    "run_id",
    "dataset_sha256",
    "repo_commit",
    "config_fingerprint",
    "db_sha256",
    "snapshot_sha256",
)


def validate_raw_identity(path: Path, identity: Mapping[str, str]) -> None:
    if not path.exists():
        return
    JsonlCheckpointWriter(path)
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if any(record.get(field) != identity.get(field) for field in _RAW_IDENTITY_FIELDS):
            raise ValueError(f"raw checkpoint identity mismatch at {path}:{line_number}")


def count_validated_records(path: Path, identity: Mapping[str, str]) -> int:
    validate_raw_identity(path, identity)
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def write_metadata(path: Path, metadata: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = sanitize_provider_metadata(metadata)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def merge_resume_metadata(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate run identity and accumulate checkpoint-safe run totals."""
    if not previous:
        result = dict(current)
        if not result.get("run_id"):
            raise ValueError("run_id must be resolved before writing metadata")
        return result
    if previous.get("dataset_sha256") != current.get("dataset_sha256"):
        raise ValueError("existing metadata dataset SHA does not match requested dataset")
    if previous.get("repo_commit") != current.get("repo_commit"):
        raise ValueError("existing metadata repository commit does not match requested commit")
    requested_run_id = current.get("run_id")
    if requested_run_id and requested_run_id != previous.get("run_id"):
        raise ValueError("explicit run_id conflicts with existing metadata")
    result = dict(current)
    result["run_id"] = previous["run_id"]
    result["records_written"] = int(current.get("records_written", 0))
    if current.get("build") is None:
        result["build"] = previous.get("build")
    result["provider_counters"] = current.get("provider_counters") or previous.get(
        "provider_counters", {}
    )
    return result


def checkpoint_completed_build(
    path: Path,
    previous: Mapping[str, Any] | None,
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    """Durably make a completed index reusable before queries begin."""
    merged = merge_resume_metadata(previous, checkpoint)
    write_metadata(path, merged)
    return merged


def reused_index_metadata(preserved: Mapping[str, Any] | None) -> dict[str, Any]:
    """Require verified build provenance before formally reusing an index."""
    if not preserved:
        raise RuntimeError(
            "Qdrant collection exists without verified build provenance; rerun with --rebuild"
        )
    original = preserved.get("original_build", preserved)
    if not isinstance(original, Mapping) or original.get("status") != "completed":
        raise RuntimeError(
            "Qdrant collection build provenance is not verifiable; rerun with --rebuild"
        )
    return {
        **dict(original),
        "status": "reused",
        "provenance_status": "verified_metadata",
        "current_embedding_batches": 0,
        "original_build": dict(original),
    }


def _collection_shape(vector_store: Any, project_id: int) -> tuple[int | None, int | None]:
    if hasattr(vector_store, "collection_info"):
        info = vector_store.collection_info(project_id)
    else:
        info = vector_store._client.get_collection(vector_store.collection_name(project_id))
    vectors = getattr(
        getattr(getattr(info, "config", None), "params", None), "vectors", None
    )
    if isinstance(vectors, Mapping):
        vector_size = next(
            (getattr(value, "size", None) for value in vectors.values()), None
        )
    else:
        vector_size = getattr(vectors, "size", None)
    return getattr(info, "points_count", None), vector_size


def verify_reusable_index(
    vector_store: Any,
    project_id: int,
    build: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    if not vector_store.has_collection(project_id):
        raise RuntimeError(
            "vector collection is missing; run --phase build or build-vector-index first"
        )
    if not build or build.get("status") not in {"completed", "reused"}:
        raise RuntimeError("verified completed build provenance is required; rerun with --rebuild")
    original = build.get("original_build", build)
    if not isinstance(original, Mapping) or original.get("status") != "completed":
        raise RuntimeError("verified completed build provenance is required; rerun with --rebuild")
    for key, value in expected.items():
        if original.get(key) != value:
            raise RuntimeError(f"vector build provenance mismatch for {key}; rerun with --rebuild")
    points_count, vector_size = _collection_shape(vector_store, project_id)
    if points_count != original.get("points_count"):
        raise RuntimeError("vector collection points_count does not match build provenance; rerun with --rebuild")
    if vector_size != original.get("vector_size"):
        raise RuntimeError("vector collection vector_size does not match build provenance; rerun with --rebuild")
    return reused_index_metadata(build)


def retrieval_config(settings: Any, args: argparse.Namespace) -> dict[str, Any]:
    """Secret-free effective settings that materially define retrieval output."""
    from app.retrieval.keyword_search import LEXICAL_IMPLEMENTATION_VERSION

    selected_variants = tuple(getattr(args, "variants", tuple(VARIANTS)))
    return {
        "qdrant_path": str(args.qdrant_path.resolve()),
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_endpoint": canonical_endpoint(settings.embedding_base_url),
        "rewrite_llm_model": settings.llm_model,
        "rewrite_llm_endpoint": canonical_endpoint(settings.llm_base_url),
        "chunk_max_content_chars": settings.chunk_max_content_chars,
        "top_k": TOP_K,
        "candidate_limit": CANDIDATE_LIMIT,
        "selected_variants": list(selected_variants),
        "lexical_implementation_version": LEXICAL_IMPLEMENTATION_VERSION,
        "variants": {
            name: variant_config(variant)
            for name in selected_variants
            for variant in (resolve_variant(name),)
        },
    }


def canonical_endpoint(value: str | None) -> str | None:
    """Return secret-free canonical endpoint identity for fingerprinting."""
    if value is None:
        return None
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        raise ValueError("provider base URL must include scheme and host")
    host_display = f"[{host}]" if ":" in host else host
    port = parsed.port
    default_port = (scheme == "https" and port == 443) or (
        scheme == "http" and port == 80
    )
    port_text = "" if port is None or default_port else f":{port}"
    return f"{scheme}://{host_display}{port_text}{parsed.path}"


def config_fingerprint(config: Mapping[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_canonical_entity_keys(
    entity_rows: Sequence[Any],
    repo_id: str,
    commit_sha: str,
) -> dict[int, str]:
    """Map volatile runtime IDs to SPEC-defined cross-run entity identities."""
    return {
        row.id: compute_stable_key(
            repo_id=repo_id,
            commit_sha=commit_sha,
            file_path=row.file_path,
            entity_type=row.entity_type,
            qualified_name=row.qualified_name,
            start_line=row.start_line,
            end_line=row.end_line,
        )
        for row in entity_rows
    }


def load_dataset(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    values = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line]
    return [case for case in values if "retrieval" in case.get("evaluation_layers", [])]


def find_pinned_project(session: Any, dataset: Sequence[Mapping[str, Any]], snapshot: Mapping[str, Any]) -> Any:
    from sqlalchemy import select
    from app.models import Project

    repo_ids = {str(case["repo_id"]) for case in dataset}
    commits = {str(case["commit_sha"]) for case in dataset}
    if repo_ids != {str(snapshot["repo_id"])}:
        raise ValueError("dataset repo_id does not match snapshot")
    if commits != {str(snapshot["commit_sha"])}:
        raise ValueError("dataset commit does not match snapshot commit")
    projects = session.scalars(select(Project).order_by(Project.id)).all()
    matches = [project for project in projects if project.id == int(snapshot["project_id"])]
    if len(matches) != 1:
        raise ValueError("pinned snapshot project was not found in evaluation database")
    project = matches[0]
    if Path(project.root_path).resolve() != Path(str(snapshot["root_path"])).resolve():
        raise ValueError("pinned project root_path does not match snapshot root_path")
    return project


def verify_repository_commit(repo_path: Path, expected: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout.strip().lower() != expected.lower():
        raise ValueError("workspace repository commit does not match pinned commit")


def compose_runtime(args: argparse.Namespace) -> tuple[RetrievalRuntime, dict[str, Any], Any, Any]:
    """Compose real backend services from an explicit env file and isolated state."""
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.graph.query_service import GraphQueryService
    from app.llm.client import OpenAICompatibleLlmClient
    from app.models import CodeEntity, CodeRelation, Project
    from app.rag.graph_retriever import GraphRagRetriever
    from app.retrieval.chunk_builder import CodeChunkBuilder
    from app.retrieval.embedding_service import (
        EmbeddingService,
        LocalSentenceTransformerProvider,
        OpenAICompatibleEmbeddingProvider,
    )
    from app.retrieval.hybrid_search import HybridSearchService
    from app.retrieval.keyword_search import KeywordSearchService
    from app.retrieval.vector_store import QdrantVectorStore

    settings = getattr(args, "settings", None) or Settings(_env_file=args.env_file)
    engine = create_engine(f"sqlite+pysqlite:///{args.db.resolve().as_posix()}", connect_args={"check_same_thread": False})
    session = Session(engine)
    dataset = load_dataset(args.dataset)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    project = find_pinned_project(session, dataset, snapshot)
    verify_repository_commit(Path(project.root_path), str(snapshot["commit_sha"]))

    embedding_http = None
    embedding_provider_counters = DurableCallCounters(
        args.ledger_dir / args.run_id / "embedding.jsonl"
    )
    if settings.embedding_provider == "api":
        raw = OpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            max_retries=0,
        )
        embedding_http = RecordingOpenAIClient(raw, embedding_provider_counters)
        provider = OpenAICompatibleEmbeddingProvider(
            settings.embedding_model,
            settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            dimensions=settings.embedding_dimensions,
            client=embedding_http,
        )
    elif settings.embedding_provider == "local":
        provider = LocalSentenceTransformerProvider(settings.embedding_model)
    else:
        raise ValueError("embedding provider must be api or local")
    embeddings = CachedEmbeddingService(EmbeddingService(provider))

    rewrite_provider_counters = DurableCallCounters(
        args.ledger_dir / args.run_id / "rewrite_llm.jsonl"
    )
    raw_llm = OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_retries=0,
    )
    llm = RecordingLlmClient(
        OpenAICompatibleLlmClient(
            settings.llm_model,
            settings.llm_api_key,
            base_url=settings.llm_base_url,
            client=raw_llm,
        ),
        rewrite_provider_counters,
    )
    rewriter = DurableRewriteCache(
        llm, args.ledger_dir / args.run_id / "rewrite_cache.jsonl"
    )
    qdrant_client = QdrantClient(path=str(args.qdrant_path.resolve()))
    vector_store = QdrantVectorStore(qdrant_client)
    keyword = KeywordSearchService(session)
    hybrid = HybridSearchService(
        embeddings=embeddings, vector_store=vector_store, keyword_search=keyword
    )
    graph_query = GraphQueryService(session)
    graph_capture = CapturingGraphTraversal(graph_query)
    graph_retriever = GraphRagRetriever(search=hybrid, graph=graph_capture)
    entity_rows = session.scalars(
        select(CodeEntity).where(CodeEntity.project_id == project.id).order_by(CodeEntity.id)
    ).all()
    relation_count = session.scalar(
        select(func.count(CodeRelation.id)).where(CodeRelation.project_id == project.id)
    )
    project_count = session.scalar(select(func.count(Project.id)))
    if int(snapshot.get("entity_count", -1)) != len(entity_rows):
        raise ValueError("snapshot entity_count does not match evaluation database")
    if int(snapshot.get("relation_count", -1)) != int(relation_count or 0):
        raise ValueError("snapshot relation_count does not match evaluation database")
    runtime = RetrievalRuntime(
        project_id=project.id,
        entity_keys=build_canonical_entity_keys(
            entity_rows,
            str(snapshot["repo_id"]),
            str(snapshot["commit_sha"]),
        ),
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=keyword,
        rewriter=rewriter,
        graph_retriever=graph_retriever,
        graph_query=graph_query,
        graph_capture=graph_capture,
        identity=args.identity,
        hybrid_search=hybrid,
    )
    build_context = {
        "settings": settings,
        "entities": entity_rows,
        "chunk_builder": CodeChunkBuilder(settings.chunk_max_content_chars),
        "embedding_http": embedding_http,
        "embedding_provider_counters": embedding_provider_counters,
        "rewrite_provider_counters": rewrite_provider_counters,
        "llm": llm,
        "dataset": dataset,
        "snapshot": snapshot,
        "relation_count": int(relation_count or 0),
        "project_count": int(project_count or 0),
    }
    return runtime, build_context, session, qdrant_client


def build_index(
    runtime: RetrievalRuntime,
    context: Mapping[str, Any],
    *,
    rebuild: bool,
    preserved: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = context["settings"]
    if runtime.vector_store.has_collection(runtime.project_id) and not rebuild:
        result = verify_reusable_index(
            runtime.vector_store,
            runtime.project_id,
            preserved,
            context["provenance"],
        )
        result["collection"] = runtime.vector_store.collection_name(runtime.project_id)
        return result
    chunks = context["chunk_builder"].build_many(context["entities"])
    before = context["embedding_http"].provider_counters.calls if context["embedding_http"] else 0
    started = time.perf_counter()
    vectors = runtime.embeddings.embed_documents([chunk.searchable_text for chunk in chunks])
    runtime.vector_store.rebuild(runtime.project_id, chunks, vectors)
    duration = time.perf_counter() - started
    after = context["embedding_http"].provider_counters.calls if context["embedding_http"] else 0
    points_count, vector_size = _collection_shape(
        runtime.vector_store, runtime.project_id
    )
    return {
        **dict(context["provenance"]),
        "status": "completed",
        "provenance_status": "measured_current_process",
        "collection": runtime.vector_store.collection_name(runtime.project_id),
        "chunks": len(chunks),
        "embedding_batches": after - before,
        "duration_seconds": duration,
        "dimension": len(vectors[0]),
        "points_count": points_count,
        "vector_size": vector_size,
        "model": settings.embedding_model,
        "qdrant_mode": "local",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Stage 2B retrieval/GraphRAG variants")
    parser.add_argument("--phase", choices=("build", "run", "all", "smoke"), default="all")
    parser.add_argument("--env-file", type=Path, default=BACKEND_DIR / ".env")
    parser.add_argument("--db", type=Path, default=ROOT / "evaluation/runtime/pilot/rca_eval.db")
    parser.add_argument("--qdrant-path", type=Path, default=ROOT / "evaluation/runtime/pilot/stage2b_qdrant")
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/pilot-current.jsonl")
    parser.add_argument("--dataset-sha", required=True)
    parser.add_argument("--repo-commit", required=True)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "evaluation/runtime/pilot/snapshot/manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results/raw/stage2b_retrieval.jsonl")
    parser.add_argument("--metadata", type=Path, default=ROOT / "evaluation/results/raw/stage2b_retrieval.metadata.json")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--variants",
        type=parse_variants,
        default=tuple(VARIANTS),
        help="ordered comma-separated retrieval variants (default: all)",
    )
    parser.add_argument(
        "--ledger-dir",
        type=Path,
        default=ROOT / "evaluation/runtime/pilot/stage2b_provider_ledgers",
    )
    parser.add_argument("--rebuild", action="store_true")
    return parser


def completed_phase_status(phase: str) -> str:
    statuses = {
        "run": "completed", "all": "completed",
        "smoke": "smoke_completed", "build": "build_completed",
    }
    if phase not in statuses:
        raise ValueError(f"unsupported retrieval phase: {phase}")
    return statuses[phase]


def main(argv: list[str] | None = None) -> int:
    from app.core.config import Settings

    args = build_parser().parse_args(argv)
    validate_selected_artifact_paths(
        args.variants, args.output, args.metadata, args.ledger_dir
    )
    dataset_sha = verify_sha256(args.dataset, args.dataset_sha)
    db_sha = sha256_file(args.db)
    snapshot_sha = sha256_file(args.snapshot)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if str(snapshot["commit_sha"]).lower() != args.repo_commit.lower():
        raise ValueError("requested repository commit does not match snapshot")
    previous_metadata = None
    if args.metadata.exists():
        previous_metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    settings = Settings(_env_file=args.env_file)
    effective_config = retrieval_config(settings, args)
    fingerprint = config_fingerprint(effective_config)
    run_id = resolve_run_id(
        previous_metadata,
        args.run_id,
        dataset_sha,
        args.repo_commit,
        db_sha,
        snapshot_sha,
        fingerprint,
    )
    args.run_id = run_id
    args.settings = settings
    args.identity = {
        "run_id": run_id,
        "dataset_sha256": dataset_sha,
        "repo_commit": args.repo_commit,
        "config_fingerprint": fingerprint,
        "db_sha256": db_sha,
        "snapshot_sha256": snapshot_sha,
    }
    existing_record_count = count_validated_records(args.output, args.identity)
    runtime, context, session, qdrant = compose_runtime(args)
    try:
        context["provenance"] = {
            "config_fingerprint": fingerprint,
            "qdrant_path": effective_config["qdrant_path"],
            "db_sha256": db_sha,
            "snapshot_sha256": snapshot_sha,
            "project_id": runtime.project_id,
            "project_count": context["project_count"],
            "entity_count": len(context["entities"]),
            "relation_count": context["relation_count"],
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
            "embedding_endpoint": effective_config["embedding_endpoint"],
            "collection": runtime.vector_store.collection_name(runtime.project_id),
        }
        should_build = args.phase in {"build", "all", "smoke"}
        needs_mutation = should_build and (
            args.rebuild or not runtime.vector_store.has_collection(runtime.project_id)
        )
        if needs_mutation:
            in_progress = {
                "status": "running",
                "phase": args.phase,
                "run_id": run_id,
                "dataset_path": str(args.dataset),
                "dataset_sha256": dataset_sha,
                "repo_commit": args.repo_commit,
                "db_sha256": db_sha,
                "snapshot_sha256": snapshot_sha,
                "config_fingerprint": fingerprint,
                "selected_variants": list(args.variants),
                "effective_config": effective_config,
                "records_written": existing_record_count,
                "build": {**context["provenance"], "status": "in_progress"},
                "provider_counters": {
                    "embedding_sdk_create_attempts": context["embedding_provider_counters"].to_dict(),
                    "rewrite_llm_sdk_create_attempts": context["rewrite_provider_counters"].to_dict(),
                },
            }
            write_metadata(
                args.metadata,
                merge_resume_metadata(previous_metadata, in_progress),
            )
        build = None
        if should_build:
            build = build_index(
                runtime,
                context,
                rebuild=args.rebuild,
                preserved=(previous_metadata or {}).get("build"),
            )
            if needs_mutation:
                previous_metadata = checkpoint_completed_build(
                    args.metadata,
                    previous_metadata,
                    {
                        "run_id": run_id,
                        "dataset_path": str(args.dataset),
                        "dataset_sha256": dataset_sha,
                        "repo_commit": args.repo_commit,
                        "db_sha256": db_sha,
                        "snapshot_sha256": snapshot_sha,
                        "config_fingerprint": fingerprint,
                        "selected_variants": list(args.variants),
                        "effective_config": effective_config,
                        "records_written": existing_record_count,
                        "build": build,
                        "provider_counters": {
                            "embedding_sdk_create_attempts": context["embedding_provider_counters"].to_dict(),
                            "rewrite_llm_sdk_create_attempts": context["rewrite_provider_counters"].to_dict(),
                        },
                    },
                )
        elif args.phase == "run":
            build = verify_reusable_index(
                runtime.vector_store,
                runtime.project_id,
                (previous_metadata or {}).get("build"),
                context["provenance"],
            )
        written = 0
        if args.phase in {"run", "all", "smoke"}:
            questions = context["dataset"][:1] if args.phase == "smoke" else context["dataset"]
            variants = (
                tuple(name for name in ("B2", "B3", "B4") if name in args.variants)
                if args.phase == "smoke"
                else args.variants
            )
            if args.phase == "smoke" and not variants:
                variants = args.variants[:1]
            if args.phase == "smoke":
                written = len(
                    run_smoke_gate(
                        questions,
                        runtime,
                        args.output,
                        variants=variants,
                    )
                )
            else:
                written = run_questions(
                    questions, runtime, args.output, variants=variants
                )
        total_records = count_validated_records(args.output, args.identity)
        embedding_http = context["embedding_http"]
        settings = context["settings"]
        metadata = {
            "status": completed_phase_status(args.phase),
            "phase": args.phase,
            "run_id": run_id,
            "dataset_path": str(args.dataset),
            "dataset_sha256": dataset_sha,
            "repo_commit": args.repo_commit,
            "db_sha256": db_sha,
            "snapshot_sha256": snapshot_sha,
            "config_fingerprint": fingerprint,
            "selected_variants": list(args.variants),
            "effective_config": effective_config,
            "project_id": runtime.project_id,
            "qdrant_mode": "local",
            "build": build,
            "records_written": total_records,
            "providers": {
                "embedding": {
                    "provider": settings.embedding_provider,
                    "model": settings.embedding_model,
                    "base_url": settings.embedding_base_url,
                    "dimensions": settings.embedding_dimensions,
                },
                "rewrite_llm": {"model": settings.llm_model, "base_url": settings.llm_base_url},
                "sdk_retries_disabled": True,
            },
            "provider_counters": {
                "embedding_sdk_create_attempts": context["embedding_provider_counters"].to_dict(),
                "rewrite_llm_sdk_create_attempts": context["rewrite_provider_counters"].to_dict(),
            },
            "provider_ledger_summary": provider_ledger_summary(
                {
                    "embedding_sdk_create_attempts": context["embedding_provider_counters"],
                    "rewrite_llm_sdk_create_attempts": context["rewrite_provider_counters"],
                }
            ),
            "process_counters": process_counter_metadata(
                runtime.embeddings, runtime.rewriter
            ),
        }
        write_metadata(
            args.metadata,
            merge_resume_metadata(previous_metadata, metadata),
        )
    except Exception as error:
        failed_metadata = {
            "status": "failed",
            "phase": args.phase,
            "run_id": run_id,
            "dataset_path": str(args.dataset),
            "dataset_sha256": dataset_sha,
            "repo_commit": args.repo_commit,
            "db_sha256": db_sha,
            "snapshot_sha256": snapshot_sha,
            "config_fingerprint": fingerprint,
            "effective_config": effective_config,
            "records_written": count_validated_records(args.output, args.identity),
            "error": {"type": type(error).__name__, "message": str(error)},
        }
        write_metadata(args.metadata, merge_resume_metadata(previous_metadata, failed_metadata))
        raise
    finally:
        session.close()
        close = getattr(qdrant, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
