# Stage 2B Real-Model Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Do not commit or push without explicit user approval.

**Goal:** Run reproducible B2-B5 and A1-A9 evaluations on the 36-record canonical Pilot using the configured real embedding and LLM providers, with isolated runtime state, deterministic metrics, raw evidence retention, stability measurement, and independent agent review.

**Architecture:** A benchmark runner composes the same backend services used by the FastAPI application against the isolated Pilot SQLite database and a dedicated local Qdrant path. Recording/caching wrappers count external calls and preserve provider metadata without logging secrets. Retrieval and Agent outputs are written as append-safe JSONL, then a separate deterministic metrics script checks the dataset SHA before scoring. Unsupported ablations are emitted as `not_executable` with a reason instead of fabricated numbers.

**Tech Stack:** Python 3.11, SQLAlchemy, Qdrant client, OpenAI-compatible embedding/LLM clients, pytest, JSONL/JSON reports.

---

### Task 1: Benchmark contracts and isolated runtime

**Files:**
- Create: `evaluation/runners/stage2b_common.py`
- Create: `evaluation/scripts/tests/test_stage2b_common.py`

- [ ] Define run metadata, JSONL checkpoint writing, dataset-SHA verification, secret-safe provider metadata, latency/call counters, and cached query rewrite/query embedding wrappers.
- [ ] Write tests for cache reuse, failed-call accounting, resume behavior, SHA mismatch refusal, and absence of API keys in serialized metadata.
- [ ] Run the focused tests and confirm the new tests fail before implementation, then pass after implementation.

### Task 2: Retrieval and graph benchmark runner

**Files:**
- Create: `evaluation/runners/stage2b_retrieval.py`
- Create: `evaluation/scripts/tests/test_stage2b_retrieval.py`

- [ ] Compose `EmbeddingService`, `QdrantVectorStore`, `KeywordSearchService`, `HybridSearchService`, `GraphRagRetriever`, and `GraphQueryService` against `evaluation/runtime/pilot/rca_eval.db`.
- [ ] Build a dedicated collection from the 2,199 scanned entities and record chunk count, batch count, build duration, model, dimensions, and Qdrant mode.
- [ ] Implement B2 vector, B3 0.7/0.3 hybrid, B4 graph expansion depth 2, A1 no rewrite, A2 0.5/0.5, A3 0.3/0.7, A4 RRF, A5 depth 0, and A6 depth 1 without changing product code.
- [ ] Persist the top-k entities/files and graph nodes/edges per question, including errors and latency.
- [ ] Test fusion arithmetic, graph-depth dispatch, source-only gold exclusion, and output contracts before any external call.

### Task 3: Full Agent and stability runner

**Files:**
- Create: `evaluation/runners/stage2b_agent.py`
- Create: `evaluation/scripts/tests/test_stage2b_agent.py`

- [ ] Compose the real deterministic planner, Code QA, Trace, Change Plan, evidence validator, GraphRAG, and LLM client using the same wiring as `agent_api.py`.
- [ ] Run B5 once for all 36 questions and two additional times for a fixed stratified 8-question stability subset.
- [ ] Record task routing, answer, references, graph evidence, uncertainties, repair/guard outcome, latency, and all failures.
- [ ] Evaluate A7 as `not_executable` if no canonical multi-turn cases exist; run A8/A9 only if product components provide a fair switch, otherwise record the exact unsupported reason.
- [ ] Test response serialization, stability-subset selection, resume behavior, and exception retention before real LLM calls.

### Task 4: Deterministic metrics and report

**Files:**
- Create: `evaluation/scripts/compute_stage2b_metrics.py`
- Create: `evaluation/scripts/generate_stage2b_report.py`
- Create: `evaluation/scripts/tests/test_compute_stage2b_metrics.py`
- Create: `evaluation/scripts/tests/test_generate_stage2b_report.py`

- [ ] Refuse inputs whose dataset SHA, repository commit, or run ID disagree.
- [ ] Compute B2/B3 file and entity Recall@1/5/10, MRR, zero-hit rate; B4 node/edge precision and recall for indexed gold; B5 routing accuracy, reference precision/recall, graph recall, citation validity, refusal/uncertainty compliance, provider failure rate, and stability Jaccard/hash statistics.
- [ ] Keep source-only and source-unanswerable diagnostics separate from main retrieval metrics.
- [ ] Report B0-B5 side by side, every ablation status, API call counts, measured latency, provider metadata, and explicit limitations. Do not infer semantic answer correctness from lexical overlap.

### Task 5: Real-provider execution with escalation control

**Files:**
- Write: `evaluation/results/raw/stage2b-*.jsonl`
- Write: `evaluation/results/metrics/stage2b_metrics.json`
- Write: `evaluation/reports/stage2b-final-report.md`

- [ ] Validate the canonical dataset and snapshot first.
- [ ] Run one document-embedding/query smoke test and one Agent case; stop on authentication, dimension, schema, or provider compatibility errors.
- [ ] Build the full vector index and run B2-B4/A1-A6.
- [ ] Run B5 and the stability subset, preserving failed cases.
- [ ] Generate metrics and report from the exact current dataset SHA.

### Task 6: Independent review and final verification

**Files:**
- Create: `evaluation/reports/stage2b-spec-audit.md`
- Create: `evaluation/reports/stage2b-results-audit.md`

- [ ] Dispatch a fresh specification-review Agent that did not implement or generate results. It checks fairness, leakage, baseline definitions, unsupported ablations, and report claims against SPEC and raw files.
- [ ] Fix every Critical/Major issue and send the same evidence back for re-review.
- [ ] Dispatch a second fresh results/code-quality Agent that checks raw-result counts, hashes, arithmetic, failure retention, secret leakage, and tests.
- [ ] Fix and re-review until no Critical/Major findings remain.
- [ ] Run evaluation tests, focused backend tests, compileall, validators, SHA reconciliation, secret scan, and `git diff --check` before reporting completion.
