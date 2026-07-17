from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


RUNNERS_DIR = Path(__file__).resolve().parents[2] / "runners"
if str(RUNNERS_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNERS_DIR))

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def hit(entity_id: int, score: float, source: str = "vector"):
    from app.retrieval.types import SearchHit

    return SearchHit(
        entity_id=entity_id,
        entity_type="java_method",
        name=f"method{entity_id}",
        qualified_name=f"Controller.method{entity_id}",
        file_path=f"src/C{entity_id}.java",
        start_line=entity_id,
        end_line=entity_id + 2,
        content="code",
        metadata={"safe": True},
        score=score,
        source=source,
    )


def test_variant_set_and_fixed_limits() -> None:
    from stage2b_retrieval import CANDIDATE_LIMIT, TOP_K, VARIANTS

    assert tuple(VARIANTS) == ("B2", "B3", "B4", "A1", "A2", "A3", "A4", "A5", "A6")
    assert TOP_K == 10
    assert CANDIDATE_LIMIT == 20
    assert VARIANTS["B2"].mode == "vector"
    assert (VARIANTS["B3"].vector_weight, VARIANTS["B3"].keyword_weight) == (0.7, 0.3)
    assert VARIANTS["B4"].graph_depth == 2
    assert VARIANTS["A1"].rewrite is False
    assert (VARIANTS["A2"].vector_weight, VARIANTS["A2"].keyword_weight) == (0.5, 0.5)
    assert (VARIANTS["A3"].vector_weight, VARIANTS["A3"].keyword_weight) == (0.3, 0.7)
    assert VARIANTS["A4"].fusion == "rrf"
    assert [VARIANTS[name].graph_depth for name in ("A5", "A6", "B4")] == [0, 1, 2]


def test_weight_sweep_variants_are_opt_in_and_cover_declared_grid() -> None:
    from stage2b_retrieval import VARIANTS, WEIGHT_SWEEP_VARIANTS, resolve_variant

    assert not (set(VARIANTS) & set(WEIGHT_SWEEP_VARIANTS))
    assert tuple(WEIGHT_SWEEP_VARIANTS) == (
        "W60", "W65", "W70", "W75", "W80", "W85", "W90", "W95"
    )
    for vector_percent in range(60, 100, 5):
        variant = resolve_variant(f"W{vector_percent}")
        assert variant.vector_weight == pytest.approx(vector_percent / 100)
        assert variant.keyword_weight == pytest.approx(1 - vector_percent / 100)
        assert variant.mode == "hybrid"
        assert variant.rewrite is True
        assert variant.fusion == "weighted"


def test_variant_cli_defaults_to_all_and_accepts_ordered_subset() -> None:
    from stage2b_retrieval import VARIANTS, build_parser

    required = ["--dataset-sha", "a" * 64, "--repo-commit", "b" * 40]

    assert build_parser().parse_args(required).variants == tuple(VARIANTS)
    assert build_parser().parse_args(
        [*required, "--variants", "B2,B3,A1,A2,A3,A4"]
    ).variants == ("B2", "B3", "A1", "A2", "A3", "A4")
    assert build_parser().parse_args(
        [*required, "--variants", "B2,W60,W75,W95"]
    ).variants == ("B2", "W60", "W75", "W95")


@pytest.mark.parametrize("value", ["", "B2,B2", "B2,UNKNOWN", "B2,"])
def test_variant_cli_rejects_empty_duplicate_or_unknown_names(value: str) -> None:
    from stage2b_retrieval import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "--dataset-sha",
                "a" * 64,
                "--repo-commit",
                "b" * 40,
                "--variants",
                value,
            ]
        )


def test_selected_variants_and_lexical_version_change_config_fingerprint() -> None:
    from stage2b_retrieval import config_fingerprint, retrieval_config

    settings = SimpleNamespace(
        embedding_provider="api",
        embedding_model="embedding-3",
        embedding_dimensions=1024,
        embedding_base_url="https://embed.example/v1",
        llm_model="chat-model",
        llm_base_url="https://llm.example/v1",
        chunk_max_content_chars=4000,
    )
    base = SimpleNamespace(qdrant_path=Path("qdrant"), variants=("B2", "B3"))
    changed = SimpleNamespace(qdrant_path=Path("qdrant"), variants=("B2",))

    config = retrieval_config(settings, base)

    assert config["selected_variants"] == ["B2", "B3"]
    assert config["lexical_implementation_version"] == "code_aware_multiterm_v2"
    assert config_fingerprint(config) != config_fingerprint(retrieval_config(settings, changed))


def test_weight_sweep_effective_weights_are_in_config_and_fingerprint() -> None:
    from stage2b_retrieval import config_fingerprint, retrieval_config

    settings = SimpleNamespace(
        embedding_provider="api",
        embedding_model="embedding-3",
        embedding_dimensions=1024,
        embedding_base_url="https://embed.example/v1",
        llm_model="chat-model",
        llm_base_url="https://llm.example/v1",
        chunk_max_content_chars=4000,
    )
    sweep = SimpleNamespace(qdrant_path=Path("qdrant"), variants=("W75", "W90"))
    different = SimpleNamespace(qdrant_path=Path("qdrant"), variants=("W75", "W95"))

    config = retrieval_config(settings, sweep)

    assert config["selected_variants"] == ["W75", "W90"]
    assert config["variants"]["W75"]["vector_weight"] == pytest.approx(0.75)
    assert config["variants"]["W75"]["keyword_weight"] == pytest.approx(0.25)
    assert config["variants"]["W90"]["vector_weight"] == pytest.approx(0.90)
    assert config["variants"]["W90"]["keyword_weight"] == pytest.approx(0.10)
    assert config_fingerprint(config) != config_fingerprint(retrieval_config(settings, different))


def test_selected_variant_run_rejects_frozen_default_result_paths() -> None:
    from stage2b_retrieval import VARIANTS, validate_selected_artifact_paths

    project_root = RUNNERS_DIR.parents[1]
    default_raw = project_root / "evaluation/results/raw/stage2b_retrieval.jsonl"
    default_metadata = project_root / "evaluation/results/raw/stage2b_retrieval.metadata.json"
    default_ledger = project_root / "evaluation/runtime/pilot/stage2b_provider_ledgers"

    with pytest.raises(ValueError, match="separate --output, --metadata, and --ledger-dir"):
        validate_selected_artifact_paths(
            ("B2", "B3"), default_raw, default_metadata, default_ledger
        )
    with pytest.raises(ValueError, match="separate --output, --metadata, and --ledger-dir"):
        validate_selected_artifact_paths(
            ("B2", "B3"),
            project_root / "evaluation/results/raw/hybrid_lexical_v2_retrieval.jsonl",
            project_root / "evaluation/results/raw/hybrid_lexical_v2_retrieval.metadata.json",
            default_ledger,
        )
    validate_selected_artifact_paths(
        ("B2", "B3"),
        project_root / "evaluation/results/raw/hybrid_lexical_v2_retrieval.jsonl",
        project_root / "evaluation/results/raw/hybrid_lexical_v2_retrieval.metadata.json",
        project_root / "evaluation/runtime/pilot/hybrid_lexical_v2_provider_ledgers",
    )
    validate_selected_artifact_paths(
        tuple(VARIANTS), default_raw, default_metadata, default_ledger
    )


def test_weighted_fusion_normalizes_sources_and_breaks_ties_by_entity_id() -> None:
    from stage2b_retrieval import weighted_fusion

    vector = [hit(2, 10), hit(1, 5)]
    keyword = [hit(1, 4, "keyword"), hit(3, 4, "keyword")]

    fused = weighted_fusion(vector, keyword, vector_weight=0.5, keyword_weight=0.5, limit=10)

    assert [(item.entity_id, item.score) for item in fused] == [
        (1, 0.75),
        (2, 0.5),
        (3, 0.5),
    ]
    assert all(item.source == "hybrid_0.5v_0.5k" for item in fused)
    assert vector[0].score == 10
    assert keyword[0].source == "keyword"


def test_b2_sorts_equal_scores_by_stable_entity_key_before_top_k() -> None:
    from stage2b_retrieval import evaluate_case

    class UnorderedVector(FakeVectorStore):
        def search(self, project_id: int, vector: list[float], limit: int):
            return [hit(entity_id, 1.0) for entity_id in range(12, 0, -1)]

    record = evaluate_case(
        {"question_id": "q", "question": "query"},
        "B2",
        fake_runtime(
            vector_store=UnorderedVector(),
            entity_keys={entity_id: f"stable-{13 - entity_id:02d}" for entity_id in range(1, 13)},
        ),
    )

    assert [item["runtime_entity_id"] for item in record["hits"]] == list(range(12, 2, -1))


def test_rrf_uses_rank_not_raw_score_and_has_deterministic_ties() -> None:
    from stage2b_retrieval import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion(
        [hit(2, 100), hit(1, 1)],
        [hit(3, 999, "keyword"), hit(1, 0.01, "keyword")],
        limit=10,
        rank_constant=60,
    )

    assert [item.entity_id for item in fused] == [1, 2, 3]
    assert fused[0].score == pytest.approx(2 / 62)
    assert fused[1].score == fused[2].score
    assert all(item.source == "rrf" for item in fused)


class FakeRewriter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def rewrite(self, query: str) -> str:
        self.calls.append(query)
        return f"rewritten:{query}"


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_query(self, query: str) -> list[float]:
        self.calls.append(query)
        return [float(len(query))]


class FakeVectorStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[int, tuple[float, ...], int]] = []
        self.fail = fail

    def search(self, project_id: int, vector: list[float], limit: int):
        self.calls.append((project_id, tuple(vector), limit))
        if self.fail:
            raise RuntimeError("vector exploded")
        return [hit(1, 1.0)]


class FakeKeyword:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[int, str, int]] = []
        self.fail = fail

    def search(self, project_id: int, query: str, limit: int):
        self.calls.append((project_id, query, limit))
        if self.fail:
            raise RuntimeError("keyword exploded")
        return [hit(2, 1.0, "keyword")]


class FakeGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int, int]] = []

    def retrieve(self, project_id: int, query: str, *, limit: int, max_depth: int):
        self.calls.append((project_id, query, limit, max_depth))
        return [
            SimpleNamespace(
                entity_id=3,
                entity_type="java_method",
                name="expanded",
                qualified_name="Service.expanded",
                file_path="src/Service.java",
                start_line=4,
                end_line=8,
                content="expanded code",
                metadata={},
                retrieval_score=0.8,
                graph_depth=max_depth,
                relation_reason="A CALLS_METHOD B",
                seed_entity_id=1,
                uncertainties=(),
            )
        ]


class FakeGraphQuery:
    def __init__(self) -> None:
        self.depths: list[int] = []

    def expand_entities(self, project_id: int, entity_ids: list[int], *, max_depth: int):
        from app.graph.types import GraphEdge, GraphNode, GraphResult

        self.depths.append(max_depth)
        return GraphResult(
            nodes=(
                GraphNode(1, "one", "java_method", "C.one", "C.java", 1, 2, "", {}),
                GraphNode(3, "three", "java_method", "S.three", "S.java", 3, 4, "", {}),
            ),
            edges=(GraphEdge(9, 1, 3, "CALLS_METHOD", 1.0, {}),),
        )


class FakeCapture:
    def __init__(self) -> None:
        self.results = []
        self.reset_calls = 0

    def reset(self) -> None:
        self.reset_calls += 1
        self.results = []

    def merged(self):
        from app.graph.types import GraphEdge, GraphNode, GraphResult

        return GraphResult(
            nodes=(
                GraphNode(1, "one", "java_method", "C.one", "C.java", 1, 2, "", {}),
                GraphNode(3, "three", "java_method", "S.three", "S.java", 3, 4, "", {}),
            ),
            edges=(GraphEdge(9, 1, 3, "CALLS_METHOD", 1.0, {}),),
        )


def fake_runtime(**overrides):
    from stage2b_retrieval import RetrievalRuntime

    values = {
        "project_id": 7,
        "entity_keys": {1: "stable-1", 2: "stable-2", 3: "stable-3"},
        "embeddings": FakeEmbeddings(),
        "vector_store": FakeVectorStore(),
        "keyword_search": FakeKeyword(),
        "rewriter": FakeRewriter(),
        "graph_retriever": FakeGraph(),
        "graph_query": FakeGraphQuery(),
        "graph_capture": FakeCapture(),
    }
    values.update(overrides)
    return RetrievalRuntime(**values)


def test_rewrite_dispatch_and_query_embedding_cache_across_variants() -> None:
    from stage2b_retrieval import evaluate_case

    runtime = fake_runtime()
    case = {"question_id": "q1", "question": "中文问题"}

    b2 = evaluate_case(case, "B2", runtime)
    b3 = evaluate_case(case, "B3", runtime)
    a1 = evaluate_case(case, "A1", runtime)

    assert b2["effective_query"] == "rewritten:中文问题"
    assert b3["effective_query"] == "rewritten:中文问题"
    assert a1["effective_query"] == "中文问题"
    assert runtime.rewriter.calls == ["中文问题"]
    assert runtime.embeddings.calls == ["rewritten:中文问题", "中文问题"]
    assert all(call[2] == 20 for call in runtime.vector_store.calls)
    assert all(call[2] == 20 for call in runtime.keyword_search.calls)


def test_weight_sweep_evaluate_case_uses_resolved_weights_without_extra_provider_calls() -> None:
    from stage2b_retrieval import evaluate_case

    runtime = fake_runtime()
    case = {"question_id": "q-weight", "question": "where is login"}

    record = evaluate_case(case, "W80", runtime)

    assert [(item["runtime_entity_id"], item["score"]) for item in record["hits"]] == [
        (1, pytest.approx(0.8)),
        (2, pytest.approx(0.2)),
    ]
    assert {item["source"] for item in record["hits"]} == {"hybrid_0.8v_0.2k"}
    assert runtime.rewriter.calls == ["where is login"]
    assert runtime.embeddings.calls == ["rewritten:where is login"]
    assert len(runtime.vector_store.calls) == 1
    assert len(runtime.keyword_search.calls) == 1


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "B2",
            {
                "mode": "vector",
                "rewrite": True,
                "vector_weight": 0.7,
                "keyword_weight": 0.3,
                "fusion": "weighted",
                "graph_depth": None,
            },
        ),
        (
            "B3",
            {
                "mode": "hybrid",
                "rewrite": True,
                "vector_weight": 0.7,
                "keyword_weight": 0.3,
                "fusion": "weighted",
                "graph_depth": None,
            },
        ),
        (
            "W80",
            {
                "mode": "hybrid",
                "rewrite": True,
                "vector_weight": 0.8,
                "keyword_weight": 0.2,
                "fusion": "weighted",
                "graph_depth": None,
            },
        ),
    ],
)
def test_raw_record_self_describes_resolved_variant_config(name: str, expected: dict) -> None:
    from stage2b_retrieval import evaluate_case

    record = evaluate_case(
        {"question_id": f"q-{name}", "question": "where is login"},
        name,
        fake_runtime(),
    )

    assert record["variant_config"] == expected


def test_hybrid_branch_diagnostics_reuse_calls_and_use_stable_deterministic_keys() -> None:
    from stage2b_retrieval import evaluate_case

    class UnorderedVector(FakeVectorStore):
        def search(self, project_id: int, vector: list[float], limit: int):
            self.calls.append((project_id, tuple(vector), limit))
            return [hit(2, 1.0), hit(1, 1.0)]

    class OverlapKeyword(FakeKeyword):
        def search(self, project_id: int, query: str, limit: int):
            self.calls.append((project_id, query, limit))
            return [hit(2, 1.0, "keyword"), hit(3, 0.9, "keyword")]

    runtime = fake_runtime(
        entity_keys={1: "stable-a", 2: "stable-b", 3: "stable-c"},
        vector_store=UnorderedVector(),
        keyword_search=OverlapKeyword(),
    )

    record = evaluate_case(
        {"question_id": "q", "question": "query"}, "B3", runtime
    )

    assert record["branch_diagnostics"] == {
        "vector_candidate_count": 2,
        "keyword_candidate_count": 2,
        "overlap_count": 1,
        "keyword_only_count": 1,
        "top10_changed_from_vector": True,
    }
    assert runtime.embeddings.calls == ["rewritten:query"]
    assert len(runtime.vector_store.calls) == 1
    assert len(runtime.keyword_search.calls) == 1


def test_graph_variants_dispatch_actual_depth_and_serialize_expansion() -> None:
    from stage2b_retrieval import evaluate_case

    runtime = fake_runtime()
    records = [evaluate_case({"question_id": "q", "question": "trace"}, name, runtime) for name in ("A5", "A6", "B4")]

    assert [call[-1] for call in runtime.graph_retriever.calls] == [0, 1, 2]
    assert runtime.graph_query.depths == []
    assert runtime.graph_capture.reset_calls == 3
    assert [record["graph_results"][0]["graph_depth"] for record in records] == [0, 1, 2]
    assert records[2]["graph_nodes"][0]["stable_entity_key"] == "stable-1"
    assert records[2]["graph_edges"] == [
        {
            "runtime_relation_id": 9,
            "source_runtime_id": 1,
            "target_runtime_id": 3,
            "source_stable_entity_key": "stable-1",
            "target_stable_entity_key": "stable-3",
            "relation_type": "CALLS_METHOD",
            "confidence": 1.0,
            "metadata": {},
        }
    ]


def test_capturing_graph_traversal_is_single_pass_and_failure_stays_uncertain() -> None:
    from app.graph.types import GraphResult
    from app.rag.graph_retriever import GraphRagRetriever
    from stage2b_retrieval import CapturingGraphTraversal

    class Search:
        def search(self, project_id: int, query: str, limit: int):
            return [hit(1, 1.0), hit(2, 0.5)]

    class Traversal:
        def __init__(self) -> None:
            self.calls = []

        def traverse(self, project_id: int, entity_id: int, *, max_depth: int, relation_types):
            self.calls.append((entity_id, max_depth))
            if entity_id == 2:
                raise RuntimeError("graph source unavailable")
            return GraphResult()

    delegate = Traversal()
    capture = CapturingGraphTraversal(delegate)
    retriever = GraphRagRetriever(search=Search(), graph=capture)

    results = retriever.retrieve(7, "trace", limit=10, max_depth=2)

    assert delegate.calls == [(1, 2), (2, 2)]
    assert len(capture.results) == 1
    failed = next(item for item in results if item.entity_id == 2)
    assert any("Graph relationship retrieval was unavailable" in item for item in failed.uncertainties)


def test_stable_hit_serialization_includes_runtime_and_stable_identity() -> None:
    from stage2b_retrieval import serialize_hit

    assert serialize_hit(hit(1, 0.75), {1: "abc"}) == {
        "runtime_entity_id": 1,
        "stable_entity_key": "abc",
        "entity_type": "java_method",
        "name": "method1",
        "qualified_name": "Controller.method1",
        "file_path": "src/C1.java",
        "start_line": 1,
        "end_line": 3,
        "score": 0.75,
        "source": "vector",
        "metadata": {"safe": True},
        "uncertainties": [],
    }


def test_source_errors_are_retained_in_raw_record() -> None:
    from stage2b_retrieval import evaluate_case

    runtime = fake_runtime(vector_store=FakeVectorStore(fail=True))
    record = evaluate_case({"question_id": "q", "question": "query"}, "B3", runtime)

    assert record["status"] == "error"
    assert record["error"]["source"] == "vector"
    assert record["error"]["type"] == "RuntimeError"
    assert "vector exploded" in record["error"]["message"]
    assert record["hits"] == []
    assert record["variant_config"] == {
        "mode": "hybrid",
        "rewrite": True,
        "vector_weight": 0.7,
        "keyword_weight": 0.3,
        "fusion": "weighted",
        "graph_depth": None,
    }
    assert record["latency_seconds"] >= 0


def test_runner_hybrid_branch_reimplementation_retains_product_fallback_contract() -> None:
    from app.retrieval.hybrid_search import HybridSearchService
    from stage2b_retrieval import evaluate_case

    class ProductVector(FakeVectorStore):
        def has_collection(self, project_id: int) -> bool:
            return True

    vector = ProductVector(fail=True)
    keyword = FakeKeyword()
    embeddings = FakeEmbeddings()
    hybrid = HybridSearchService(
        embeddings=embeddings,
        vector_store=vector,
        keyword_search=keyword,
    )
    runtime = fake_runtime(
        embeddings=embeddings,
        vector_store=vector,
        keyword_search=keyword,
        hybrid_search=hybrid,
    )

    record = evaluate_case({"question_id": "q", "question": "query"}, "B3", runtime)

    assert record["status"] == "ok"
    assert record["hits"][0]["source"] == "keyword_fallback"
    assert any("Vector retrieval was unavailable" in item for item in record["hits"][0]["uncertainties"])
    assert record["branch_diagnostics"] == {
        "vector_candidate_count": 0,
        "keyword_candidate_count": 1,
        "overlap_count": 0,
        "keyword_only_count": 1,
        "top10_changed_from_vector": True,
    }
    assert embeddings.calls == ["rewritten:query"]
    assert len(vector.calls) == 1
    assert len(keyword.calls) == 1


def test_keyword_domain_error_is_not_converted_to_vector_fallback() -> None:
    from app.errors import DomainError
    from app.retrieval.hybrid_search import HybridSearchService
    from stage2b_retrieval import evaluate_case

    class DomainFailingKeyword(FakeKeyword):
        def search(self, project_id: int, query: str, limit: int):
            self.calls.append((project_id, query, limit))
            raise DomainError(code="PROJECT_NOT_FOUND", message="missing", status_code=404)

    vector = FakeVectorStore()
    keyword = DomainFailingKeyword()
    embeddings = FakeEmbeddings()
    hybrid = HybridSearchService(
        embeddings=embeddings, vector_store=vector, keyword_search=keyword
    )
    record = evaluate_case(
        {"question_id": "q", "question": "query"},
        "B3",
        fake_runtime(
            embeddings=embeddings,
            vector_store=vector,
            keyword_search=keyword,
            hybrid_search=hybrid,
        ),
    )

    assert record["status"] == "error"
    assert record["error"]["type"] == "DomainError"
    assert "branch_diagnostics" not in record


def test_resume_skips_completed_records_without_requery(tmp_path: Path) -> None:
    from stage2b_retrieval import run_questions

    output = tmp_path / "raw.jsonl"
    output.write_text(
        json.dumps({"question_id": "q1", "variant": "B2", "run_index": 0}) + "\n",
        encoding="utf-8",
    )
    runtime = fake_runtime()

    written = run_questions(
        [{"question_id": "q1", "question": "query"}],
        runtime,
        output,
        variants=("B2", "A1"),
    )

    assert written == 1
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [(r["question_id"], r["variant"]) for r in records] == [("q1", "B2"), ("q1", "A1")]
    assert len(runtime.vector_store.calls) == 1


def test_metadata_writer_drops_secret_values(tmp_path: Path) -> None:
    from stage2b_retrieval import write_metadata

    path = tmp_path / "metadata.json"
    write_metadata(
        path,
        {
            "run_id": "run-1",
            "dataset_sha256": "a" * 64,
            "repo_commit": "b" * 40,
            "providers": {"embedding": {"model": "embedding-3", "api_key": "LEAK"}},
            "provider_counters": {"embedding": {"calls": 2}},
        },
    )

    encoded = path.read_text(encoding="utf-8")
    assert "embedding-3" in encoded
    assert "LEAK" not in encoded
    assert "api_key" not in encoded.lower()


def test_find_pinned_project_verifies_snapshot_and_dataset_commit() -> None:
    from stage2b_retrieval import find_pinned_project

    project = SimpleNamespace(id=1, name="ruoyi-vue", root_path="repo")
    session = SimpleNamespace(scalars=lambda statement: SimpleNamespace(all=lambda: [project]))
    dataset = [{"repo_id": "ruoyi-vue", "commit_sha": "c" * 40}]
    snapshot = {
        "repo_id": "ruoyi-vue",
        "commit_sha": "c" * 40,
        "project_id": 1,
        "root_path": "repo",
    }

    assert find_pinned_project(session, dataset, snapshot) is project
    with pytest.raises(ValueError, match="commit"):
        find_pinned_project(session, dataset, {**snapshot, "commit_sha": "d" * 40})
    with pytest.raises(ValueError, match="root_path"):
        find_pinned_project(session, dataset, {**snapshot, "root_path": "different"})


def test_metadata_resume_accumulates_counters_and_preserves_run_and_build() -> None:
    from stage2b_retrieval import merge_resume_metadata

    previous = {
        "run_id": "stable-run",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "records_written": 12,
        "build": {"status": "rebuilt", "chunks": 99, "dimension": 3},
        "provider_counters": {"embedding_http": {"calls": 4, "successes": 4, "failures": 0, "latency_seconds": 2.0}},
    }
    current = {
        "run_id": None,
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "records_written": 3,
        "build": None,
        "provider_counters": {"embedding_http": {"calls": 2, "successes": 1, "failures": 1, "latency_seconds": 1.5}},
    }

    merged = merge_resume_metadata(previous, current)

    assert merged["run_id"] == "stable-run"
    assert merged["records_written"] == 3
    assert merged["build"] == previous["build"]
    assert merged["provider_counters"]["embedding_http"] == {
        "calls": 2,
        "successes": 1,
        "failures": 1,
        "latency_seconds": 1.5,
    }
    with pytest.raises(ValueError, match="run_id"):
        merge_resume_metadata(previous, {**current, "run_id": "conflict"})
    with pytest.raises(ValueError, match="dataset"):
        merge_resume_metadata(previous, {**current, "dataset_sha256": "c" * 64})


def test_reused_index_metadata_requires_and_preserves_verified_provenance() -> None:
    from stage2b_retrieval import reused_index_metadata

    preserved = {
        "status": "completed",
        "chunks": 2199,
        "embedding_batches": 35,
        "duration_seconds": 10.0,
        "dimension": 1024,
        "model": "embedding-3",
        "qdrant_mode": "local",
    }
    assert reused_index_metadata(preserved) == {
        **preserved,
        "status": "reused",
        "provenance_status": "verified_metadata",
        "current_embedding_batches": 0,
        "original_build": preserved,
    }
    with pytest.raises(RuntimeError, match="--rebuild"):
        reused_index_metadata(None)


def test_gold_fields_do_not_change_retrieval_execution() -> None:
    from stage2b_retrieval import evaluate_case

    plain_runtime = fake_runtime()
    gold_runtime = fake_runtime()
    plain = evaluate_case({"question_id": "q", "question": "query"}, "B3", plain_runtime)
    with_gold = evaluate_case(
        {
            "question_id": "q",
            "question": "query",
            "gold_entities": [{"stable_entity_key": "gold"}],
            "source_only": [{"stable_entity_key": "not-indexed"}],
        },
        "B3",
        gold_runtime,
    )

    for field in (
        "latency_seconds",
        "retrieval_latency_seconds",
        "wall_latency_seconds",
    ):
        plain.pop(field)
        with_gold.pop(field)
    assert plain == with_gold
    assert plain_runtime.vector_store.calls == gold_runtime.vector_store.calls
    assert plain_runtime.keyword_search.calls == gold_runtime.keyword_search.calls


def test_durable_call_counters_replay_events_across_process_instances(
    tmp_path: Path,
) -> None:
    from stage2b_retrieval import DurableCallCounters

    ledger = tmp_path / "run-1" / "embedding.jsonl"
    first = DurableCallCounters(ledger)
    first.record_success(0.25)
    first.record_failure(0.75)

    replayed = DurableCallCounters(ledger)

    assert replayed.to_dict() == {
        "calls": 2,
        "successes": 1,
        "failures": 1,
        "latency_seconds": 1.0,
        "pending": 0,
        "unconfirmed": 0,
    }
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [event["outcome"] for event in events] == ["success", "failure"]


def test_durable_call_counter_materializes_empty_replayable_ledger(
    tmp_path: Path,
) -> None:
    from stage2b_retrieval import DurableCallCounters

    ledger = tmp_path / "run-empty" / "rewrite_llm.jsonl"
    counter = DurableCallCounters(ledger)

    assert ledger.is_file()
    assert ledger.read_bytes() == b""
    expected = {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "latency_seconds": 0.0,
        "pending": 0,
        "unconfirmed": 0,
    }
    assert counter.to_dict() == expected
    assert DurableCallCounters(ledger).to_dict() == expected


def test_zero_call_embedding_and_rewrite_ledgers_are_hashable_without_counting_calls(
    tmp_path: Path,
) -> None:
    from stage2b_common import sha256_file
    from stage2b_retrieval import DurableCallCounters

    run_dir = tmp_path / "run-zero-provider"
    embedding = DurableCallCounters(run_dir / "embedding.jsonl")
    rewrite = DurableCallCounters(run_dir / "rewrite_llm.jsonl")

    assert sha256_file(embedding.path) == sha256_file(rewrite.path)
    assert embedding.path.stat().st_size == rewrite.path.stat().st_size == 0
    assert embedding.calls == rewrite.calls == 0
    assert embedding.successes == rewrite.successes == 0
    assert embedding.failures == rewrite.failures == 0
    assert embedding.pending == rewrite.pending == 0
    assert embedding.unconfirmed == rewrite.unconfirmed == 0


def test_durable_call_counter_fsyncs_each_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stage2b_retrieval import DurableCallCounters

    calls: list[int] = []
    monkeypatch.setattr(os, "fsync", calls.append)
    counter = DurableCallCounters(tmp_path / "events.jsonl")

    assert len(calls) == 1

    counter.record_success(0.1)

    assert len(calls) == 2


def test_first_run_identity_is_deterministic_for_interruption_replay(
    tmp_path: Path,
) -> None:
    from stage2b_retrieval import DurableCallCounters, resolve_run_id

    dataset_sha = "a" * 64
    commit = "b" * 40
    first_id = resolve_run_id(None, None, dataset_sha, commit)
    first = DurableCallCounters(tmp_path / first_id / "embedding.jsonl")
    first.record_success(0.5)

    resumed_id = resolve_run_id(None, None, dataset_sha, commit)
    resumed = DurableCallCounters(tmp_path / resumed_id / "embedding.jsonl")

    assert resumed_id == first_id
    assert resumed.calls == 1


def test_phase_run_requires_existing_verified_collection() -> None:
    from stage2b_retrieval import verify_reusable_index

    class Store:
        def has_collection(self, project_id: int) -> bool:
            return False

    with pytest.raises(RuntimeError, match="build-vector|--phase build"):
        verify_reusable_index(Store(), 1, None, {})


def test_raw_checkpoint_identity_mismatch_refuses_before_resume(tmp_path: Path) -> None:
    from stage2b_retrieval import validate_raw_identity

    identity = {
        "run_id": "run-a",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "config_fingerprint": "c" * 64,
        "db_sha256": "d" * 64,
        "snapshot_sha256": "e" * 64,
    }
    output = tmp_path / "raw.jsonl"
    output.write_text(
        json.dumps(
            {
                "question_id": "q",
                "variant": "B2",
                "run_index": 0,
                **{**identity, "db_sha256": "e" * 64},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="raw checkpoint identity"):
        validate_raw_identity(output, identity)


def test_run_questions_adds_strong_identity_to_every_record(tmp_path: Path) -> None:
    from stage2b_retrieval import run_questions

    identity = {
        "run_id": "run-a",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "config_fingerprint": "c" * 64,
        "db_sha256": "d" * 64,
        "snapshot_sha256": "e" * 64,
    }
    runtime = fake_runtime(identity=identity)

    run_questions(
        [{"question_id": "q", "question": "query"}],
        runtime,
        tmp_path / "raw.jsonl",
        variants=("B2",),
    )

    record = json.loads((tmp_path / "raw.jsonl").read_text(encoding="utf-8"))
    assert {key: record[key] for key in identity} == identity


def test_resume_refuses_config_or_database_mismatch() -> None:
    from stage2b_retrieval import resolve_run_id

    previous = {
        "run_id": "stable",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "db_sha256": "d" * 64,
        "snapshot_sha256": "e" * 64,
        "config_fingerprint": "f" * 64,
    }
    with pytest.raises(ValueError, match="database"):
        resolve_run_id(previous, None, "a" * 64, "b" * 40, "x" * 64, "e" * 64, "f" * 64)
    with pytest.raises(ValueError, match="config"):
        resolve_run_id(previous, None, "a" * 64, "b" * 40, "d" * 64, "e" * 64, "x" * 64)


def test_canonical_endpoint_strips_secrets_but_preserves_endpoint_identity() -> None:
    from stage2b_retrieval import canonical_endpoint

    assert canonical_endpoint(
        "HTTPS://user:password@Example.COM:443/v1/embed?api_key=secret#fragment"
    ) == "https://example.com/v1/embed"
    assert canonical_endpoint("https://Example.com:8443/v1/") == "https://example.com:8443/v1/"
    identities = {
        canonical_endpoint("http://example.com/v1"),
        canonical_endpoint("https://example.com/v1"),
        canonical_endpoint("https://example.com:8443/v1"),
        canonical_endpoint("https://example.com/v2"),
    }
    assert len(identities) == 4


def test_records_written_reconciles_from_validated_raw_checkpoint(tmp_path: Path) -> None:
    from stage2b_retrieval import count_validated_records

    identity = {
        "run_id": "run",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "config_fingerprint": "c" * 64,
        "db_sha256": "d" * 64,
        "snapshot_sha256": "e" * 64,
    }
    path = tmp_path / "raw.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({**identity, "question_id": f"q{i}", "variant": "B2", "run_index": 0})
            for i in range(3)
        )
        + "\n",
        encoding="utf-8",
    )

    assert count_validated_records(path, identity) == 3


def test_reuse_rejects_stale_or_partial_collection_provenance() -> None:
    from stage2b_retrieval import verify_reusable_index

    info = SimpleNamespace(
        points_count=9,
        config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=3))),
    )

    class Store:
        def has_collection(self, project_id: int) -> bool:
            return True

        def collection_info(self, project_id: int):
            return info

    expected = {
        "status": "completed",
        "points_count": 10,
        "vector_size": 3,
        "config_fingerprint": "f",
    }
    with pytest.raises(RuntimeError, match="points_count"):
        verify_reusable_index(Store(), 1, expected, {"config_fingerprint": "f"})
    with pytest.raises(RuntimeError, match="completed"):
        verify_reusable_index(Store(), 1, {**expected, "status": "in_progress"}, {"config_fingerprint": "f"})


def test_durable_rewrite_cache_persists_success_and_degradation(tmp_path: Path) -> None:
    from stage2b_retrieval import DurableRewriteCache

    class Llm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            if "失败" in user_prompt:
                raise RuntimeError("provider down")
            return " English   keywords "

    llm = Llm()
    ledger = tmp_path / "rewrite.jsonl"
    cache = DurableRewriteCache(llm, ledger)
    assert cache.rewrite("中文问题") == "English keywords"
    assert cache.rewrite("失败问题") == "失败问题"
    assert cache.rewrite("english query") == "english query"
    replay = DurableRewriteCache(SimpleNamespace(complete=lambda *_: pytest.fail("called")), ledger)
    assert replay.rewrite("中文问题") == "English keywords"
    degraded = replay.details("失败问题")
    assert degraded["rewrite_degraded"] is True
    assert degraded["rewrite_error"]["type"] == "RuntimeError"
    assert llm.calls == 2


def test_rewrite_latency_is_logically_charged_to_each_enabled_variant() -> None:
    from stage2b_retrieval import evaluate_case

    class Rewriter(FakeRewriter):
        def details(self, query: str):
            return {
                "rewrite_latency_seconds": 0.25,
                "rewrite_degraded": False,
                "rewrite_error": None,
            }

    runtime = fake_runtime(rewriter=Rewriter())
    b2 = evaluate_case({"question_id": "q", "question": "中文"}, "B2", runtime)
    b3 = evaluate_case({"question_id": "q", "question": "中文"}, "B3", runtime)
    a1 = evaluate_case({"question_id": "q", "question": "中文"}, "A1", runtime)

    assert b2["rewrite_latency_seconds"] == b3["rewrite_latency_seconds"] == 0.25
    assert a1["rewrite_latency_seconds"] == 0
    assert b2["latency_seconds"] == pytest.approx(
        b2["rewrite_latency_seconds"] + b2["retrieval_latency_seconds"]
    )


def test_atomic_metadata_uses_replace_and_fsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from stage2b_retrieval import write_metadata

    replaces = []
    fsyncs = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda source, target: (replaces.append((source, target)), real_replace(source, target))[1])
    monkeypatch.setattr(os, "fsync", fsyncs.append)

    target = tmp_path / "metadata.json"
    write_metadata(target, {"run_id": "run"})

    assert len(replaces) == 1
    assert len(fsyncs) >= 1
    assert json.loads(target.read_text(encoding="utf-8"))["run_id"] == "run"


def test_completed_build_is_checkpointed_before_long_running_queries(tmp_path: Path) -> None:
    from stage2b_retrieval import checkpoint_completed_build

    checkpoint = {
        "run_id": "run",
        "dataset_sha256": "a" * 64,
        "repo_commit": "b" * 40,
        "records_written": 0,
        "build": {"status": "completed", "points_count": 10},
        "provider_counters": {},
    }
    path = tmp_path / "metadata.json"

    returned = checkpoint_completed_build(path, None, checkpoint)

    assert returned["build"]["status"] == "completed"
    assert json.loads(path.read_text(encoding="utf-8"))["build"]["status"] == "completed"


def test_retrieval_phase_status_distinguishes_formal_smoke_and_build() -> None:
    from stage2b_retrieval import completed_phase_status

    assert completed_phase_status("run") == "completed"
    assert completed_phase_status("all") == "completed"
    assert completed_phase_status("smoke") == "smoke_completed"
    assert completed_phase_status("build") == "build_completed"


def test_durable_counter_quarantines_only_torn_final_event(tmp_path: Path) -> None:
    from stage2b_retrieval import DurableCallCounters

    ledger = tmp_path / "events.jsonl"
    valid = json.dumps({"outcome": "success", "latency_seconds": 0.2}) + "\n"
    ledger.write_bytes(valid.encode() + b'{"outcome":"failure"')

    replay = DurableCallCounters(ledger)

    assert replay.calls == 1
    assert Path(f"{ledger}.torn").exists()
    ledger.write_text(valid + "not-json\n" + valid, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid provider event ledger"):
        DurableCallCounters(ledger)


def test_durable_counter_normalizes_valid_unterminated_final_event(tmp_path: Path) -> None:
    from stage2b_retrieval import DurableCallCounters

    ledger = tmp_path / "events.jsonl"
    ledger.write_text(
        json.dumps({"outcome": "success", "latency_seconds": 0.1}),
        encoding="utf-8",
    )

    counter = DurableCallCounters(ledger)
    counter.record_failure(0.2)

    assert DurableCallCounters(ledger).to_dict()["calls"] == 2


def test_process_counter_metadata_supports_durable_rewrite_cache(tmp_path: Path) -> None:
    from stage2b_common import CallCounters
    from stage2b_retrieval import DurableRewriteCache, process_counter_metadata

    embeddings = SimpleNamespace(
        delegate_counters=CallCounters(calls=2, successes=2, latency_seconds=0.3)
    )
    rewrite_cache = DurableRewriteCache(
        SimpleNamespace(complete=lambda *_: "rewritten"),
        tmp_path / "rewrite.jsonl",
    )
    rewrite_cache.rewrite("中文问题")

    assert process_counter_metadata(embeddings, rewrite_cache) == {
        "embedding_service": {
            "calls": 2,
            "successes": 2,
            "failures": 0,
            "latency_seconds": 0.3,
        },
        "rewrite_cache_entries": 1,
    }


def test_provider_ledger_summary_uses_durable_counter_state() -> None:
    from stage2b_retrieval import provider_ledger_summary

    counters = {
        "embedding_sdk_create_attempts": SimpleNamespace(pending=0, unconfirmed=0),
        "rewrite_llm_sdk_create_attempts": SimpleNamespace(pending=1, unconfirmed=1),
    }

    assert provider_ledger_summary(counters) == {
        "embedding_sdk_create_attempts": {
            "pending": 0,
            "unconfirmed": 0,
            "orphan": 0,
        },
        "rewrite_llm_sdk_create_attempts": {
            "pending": 1,
            "unconfirmed": 1,
            "orphan": 1,
        },
    }


def test_real_pilot_row_maps_to_canonical_gold_stable_entity_key() -> None:
    from stage2b_retrieval import build_canonical_entity_keys

    root = Path(__file__).resolve().parents[3]
    database = root / "evaluation/runtime/pilot/rca_eval.db"
    dataset = root / "evaluation/datasets/pilot-current.jsonl"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT id, entity_key, file_path, entity_type, qualified_name,
                   start_line, end_line
            FROM code_entities
            WHERE qualified_name = 'SysLoginController.login'
            """
        ).fetchone()
    assert row is not None
    entity = SimpleNamespace(
        id=row[0],
        entity_key=row[1],
        file_path=row[2],
        entity_type=row[3],
        qualified_name=row[4],
        start_line=row[5],
        end_line=row[6],
    )
    gold = next(
        gold_entity
        for line in dataset.read_text(encoding="utf-8").splitlines()
        for gold_entity in json.loads(line).get("gold_entities", [])
        if gold_entity.get("qualified_name") == "SysLoginController.login"
    )

    mapping = build_canonical_entity_keys(
        [entity],
        "ruoyi-vue",
        "41720e624c5a668c7d3777835e4c87095a7a1dfd",
    )

    assert mapping[entity.id] == gold["stable_entity_key"]
    assert len(mapping[entity.id]) == 64
    assert all(character in "0123456789abcdef" for character in mapping[entity.id])
    assert entity.entity_key != mapping[entity.id]


def test_durable_attempt_replay_exposes_unconfirmed_call_after_crash(tmp_path: Path) -> None:
    from stage2b_retrieval import DurableCallCounters

    ledger = tmp_path / "attempts.jsonl"
    first = DurableCallCounters(ledger)
    attempt_id = first.begin_attempt()

    replayed = DurableCallCounters(ledger)

    assert replayed.calls == 1
    assert replayed.pending == 1
    assert replayed.unconfirmed == 1
    replayed.finish_attempt(attempt_id, "failure", 0.4)
    assert DurableCallCounters(ledger).to_dict() == {
        "calls": 1,
        "successes": 0,
        "failures": 1,
        "latency_seconds": 0.4,
        "pending": 0,
        "unconfirmed": 0,
    }


def test_durable_attempt_replay_rejects_unknown_finish_even_without_newline(
    tmp_path: Path,
) -> None:
    from stage2b_retrieval import DurableCallCounters

    ledger = tmp_path / "attempts.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "event": "finished",
                "attempt_id": "unknown",
                "outcome": "success",
                "latency_seconds": 0.1,
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid provider event ledger"):
        DurableCallCounters(ledger)
    assert not Path(f"{ledger}.torn").exists()


def test_smoke_failure_isolated_without_touching_canonical_output(tmp_path: Path) -> None:
    from stage2b_retrieval import run_smoke_gate

    canonical = tmp_path / "canonical.jsonl"
    canonical.write_bytes(b"original canonical bytes\n")
    runtime = fake_runtime(vector_store=FakeVectorStore(fail=True))

    with pytest.raises(RuntimeError, match="smoke retrieval failed"):
        run_smoke_gate(
            [{"question_id": "q", "question": "query"}],
            runtime,
            canonical,
            variants=("B2",),
        )

    assert canonical.read_bytes() == b"original canonical bytes\n"
    failed = list(tmp_path.glob("canonical.smoke-failed-*.jsonl"))
    assert len(failed) == 1
    assert json.loads(failed[0].read_text(encoding="utf-8"))["status"] == "error"


def test_successful_smoke_promotes_exact_records_for_full_resume(tmp_path: Path) -> None:
    from stage2b_retrieval import run_questions, run_smoke_gate

    canonical = tmp_path / "canonical.jsonl"
    runtime = fake_runtime()

    promoted = run_smoke_gate(
        [{"question_id": "q", "question": "query"}],
        runtime,
        canonical,
        variants=("B2",),
    )
    calls_after_smoke = len(runtime.vector_store.calls)
    written = run_questions(
        [{"question_id": "q", "question": "query"}],
        runtime,
        canonical,
        variants=("B2",),
    )

    assert written == 0
    assert len(runtime.vector_store.calls) == calls_after_smoke
    assert json.loads(canonical.read_text(encoding="utf-8")) == promoted[0]


def test_rewrite_cache_and_retrieval_raw_redact_error_credentials(tmp_path: Path) -> None:
    from stage2b_retrieval import DurableRewriteCache, evaluate_case

    secret_message = (
        "Bearer bearer-secret api_key=key-secret "
        "https://user:pass@example.test/v1?token=url-secret"
    )

    class FailingLlm:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError(secret_message)

    cache_path = tmp_path / "rewrite.jsonl"
    cache = DurableRewriteCache(FailingLlm(), cache_path)
    cache.rewrite("中文查询")
    cache_encoded = cache_path.read_text(encoding="utf-8")

    class SecretVector(FakeVectorStore):
        def search(self, project_id: int, vector: list[float], limit: int):
            raise RuntimeError(secret_message)

    record = evaluate_case(
        {"question_id": "q", "question": "query"},
        "B2",
        fake_runtime(vector_store=SecretVector()),
    )
    raw_encoded = json.dumps(record)

    for encoded in (cache_encoded, raw_encoded):
        assert "bearer-secret" not in encoded
        assert "key-secret" not in encoded
        assert "url-secret" not in encoded
        assert "user:pass" not in encoded
        assert "[REDACTED]" in encoded
