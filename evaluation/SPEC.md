# ResearchCode-Agent Evaluation Specification

**Version:** 1.1.0-draft
**Created:** 2026-07-15
**Status:** Stage 1.1 revised

---

## Changelog

### v1.1.0-draft (Stage 1.1 revised)

Eleven corrections applied to the v1.0.0-draft specification:

1. **Fix 1 -- README discrepancy claim removed:** Section 2.2 item 3 now acknowledges that the project README already documents the `affected_files` design choice, rather than flagging it as an undocumented limitation.
2. **Fix 2 -- annotator != reviewer enforcement clarified:** Section 9.1 item 6 now states this is enforced by semantic validation in `validate_dataset.py`, not by JSON Schema (Draft-07 cannot express cross-field inequality).
3. **Fix 3 -- LLM determinism claim corrected:** Section 11 risk row now states that `temperature=0` reduces but does not guarantee determinism, and specifies full metadata recording plus a stability subset for variance measurement.
4. **Fix 5 -- SPEC and manifest aligned:** Section 4.2 no longer duplicates the candidate list; it references `repos/manifest.yaml` as the authoritative source and provides a brief summary.
5. **Fix 6 -- sample-project provenance:** New Section 7.4 documents the internal test fixture's provenance and usage constraints.
6. **Fix 7 -- stable_entity_key definition:** New Section 7.5 defines the stable entity key used in gold labels instead of volatile database auto-increment IDs.
7. **Fix 8 -- Enhanced conditional validation rules:** New Section 9.3 lists all semantic validation rules enforced beyond JSON Schema.
8. **Fix 9 -- required_claims evidence format:** Section 7.2 now notes that `required_claims` uses `evidence_ranges` (array of `{file_path, start_line, end_line}`) rather than flat `evidence_lines`.
9. **Fix 10 -- Fixed Pilot count:** Section 10.2 now specifies exactly 36 questions with cross-cutting dimension distributions.
10. **Fix 11 -- Change Plan gold label objectivity:** Section 3.E now defines two case types (historical-change and expert-annotated hypothetical) with explicit selection criteria and metric naming.
11. **Version and status updated** to reflect the revised draft.

---

## 1. Evaluation Objectives

This evaluation framework answers eight core questions about ResearchCode-Agent's
value proposition, component effectiveness, and failure boundaries. Each question
maps to specific measurable metrics across five evaluation layers.

### 1.1 Core Questions

| ID | Question | Primary Layers | Key Metrics |
|----|----------|---------------|-------------|
| Q1 | Why not grep/IDE/keyword? | Retrieval (B) | Recall@K vs B0 baseline |
| Q2 | Is vector > keyword? | Retrieval (B) | B1 vs B2 comparison |
| Q3 | Is hybrid > either alone? | Retrieval (B) | B3 vs B1/B2 ablation |
| Q4 | Does GraphRAG help tracing? | Graph/Trace (C) | B4 vs B3, node/edge P/R |
| Q5 | Does unified Agent add value? | Answer (D), Routing (A) | B5 vs B4, routing accuracy |
| Q6 | Do citations reduce hallucination? | Answer (D) | Unsupported claim rate |
| Q7 | Where does the system fail? | All layers | Failure catalog |
| Q8 | Are components worth their cost? | Performance (Section 8) | Latency/cost vs accuracy |

---

## 2. System Under Test

### 2.1 Evaluable Capabilities

Based on Stage 0 code analysis, the following capabilities are testable:

**Source Parsing (3 languages):**
- Java: classes, methods, Spring `@RequestMapping`/`@GetMapping`/`@PostMapping`,
  `@Service`, constructor injection, `@Autowired`/`@Resource` field injection
- Python: classes, functions, decorators, async functions, nested definitions
- Vue/JS/TS: static HTTP calls (axios, request wrapper, fetch), dynamic URL
  detection, TypeScript member methods

**Static Relations (4 types):**
- `CONTAINS`: class -> method (all parsers)
- `DEFINES_API`: Spring controller method -> backend_api entity
- `REQUESTS_API`: frontend HTTP call -> backend_api entity (with path normalization)
- `CALLS_METHOD`: method call -> target method (receiver_type resolution, unique
  name disambiguation, ambiguous-call recording)

**Retrieval (3 modes):**
- Keyword search: SQL LIKE with field-weighted scoring (name=1.0, qualified_name=0.9,
  name_substring=0.75, file_path=0.6, content=0.4)
- Vector search: Qdrant cosine similarity over code chunk embeddings
- Hybrid search: max-score normalization, 0.7*vector + 0.3*keyword, dedup by entity_id

**Query Rewriting:**
- CJK detection triggers Chinese-to-English LLM rewrite
- English queries bypass rewriting

**Graph Traversal:**
- BFS from seed entities, max depth configurable (default 2)
- Follows REQUESTS_API, DEFINES_API, CALLS_METHOD edges
- SQLite-backed, no external graph database

**RAG Context Building:**
- Ranked context with `[n] file:start-end` citations
- 12,000 character budget
- Conversation memory: last 6 messages, 600 chars each, 4000 chars total

**Evidence Validation:**
- Citation ID verification against provided references
- File path verification against reference set
- Line range verification against indexed entities
- One-round repair on validation failure
- Fallback to "evidence validation failed" message

**Task Routing (deterministic):**
- CHANGE_PLAN: keywords "modify", "add", "change", "impact", "risk", "affected"
  + Chinese equivalents
- TRACE_CHAIN: keywords "call chain", "trace", "data flow", "frontend backend"
  + Chinese equivalents
- CODE_QA: keywords "where", "which file", "implementation" + Chinese equivalents;
  also the default fallback

### 2.2 Known Limitations (from code analysis)

1. Planner is keyword-based, not LLM-based
2. Tool registry exists but dynamic tool selection is not implemented
3. Change plan `affected_files` is intentionally not exposed in the unified
   `/api/agent/chat` response. This design choice is already documented in the
   project README (`agents.md` > "Known important limitations"). The evaluation
   tracks this as a known constraint, not an undocumented gap.
4. Static analysis misses: reflection, dynamic dispatch, runtime routing, proxies,
   AOP, `@Bean` factory methods, `ApplicationContext.getBean()`
5. CALLS_METHOD requires unique method name per class for resolution
6. Frontend request resolution: dynamic URLs produce warnings, not relations
7. Conversation memory is not injected into RAG prompts as semantic context
8. Vector index must be manually rebuilt after source changes
9. No cross-project analysis support
10. Keyword search uses SQL LIKE (no full-text search, no BM25)

---

## 3. Evaluation Layers

### 3.A Task Routing

**Goal:** Verify that questions are correctly routed to CODE_QA, TRACE_CHAIN,
or CHANGE_PLAN.

**Test Design:**
- Input: question text (zh/en), expected task_type
- Output: predicted task_type from SimpleAgentPlanner.plan()
- No external dependencies; pure deterministic logic test

**Metrics:**
- Accuracy (overall)
- Macro F1 (across 3 classes)
- Confusion matrix (3x3)
- Per-language accuracy (zh, en)
- Failure cases: ambiguous questions, multi-intent questions, questions that
  should be rejected

**Special Samples:**
- Questions matching multiple task-type keywords (priority test)
- Questions with no task-type keywords (default routing)
- Questions that are not code-related at all (should still route, but note)
- Chinese questions with colloquial phrasing

### 3.B Retrieval

**Goal:** Measure whether the right code entities are retrieved for different
query types.

**Test Design:**
- Input: query text, project_id, gold entity set
- Output: ranked list of (entity_id, score, source)
- Gold label: must_recall entities, acceptable_alternatives, insufficient entities,
  distractor entities

**Query Types:**
1. Exact symbol (class name, method name, API path)
2. Natural language function description
3. Chinese query
4. English query
5. API path query (`/api/alerts`)
6. Functional query without class names
7. Synonym queries (different words, same concept)
8. Query with distractor terms

**Metrics:**
- Recall@1, Recall@5, Recall@10
- MRR (Mean Reciprocal Rank)
- nDCG@10 (when graded relevance is available)
- Zero-hit rate (percentage of queries with zero relevant results)
- Per-query-type grouped metrics

**Baselines:**
- B0: ripgrep text search (simulated via KeywordSearchService with content-only matching)
- B1: Keyword search only
- B2: Vector search only
- B3: Hybrid search (current default)

### 3.C Static Graph / Trace Chain

**Goal:** Measure whether call-chain tracing produces correct and complete chains.

**Test Design:**
- Input: trace question, project_id, gold chain
- Output: ordered nodes, ordered edges, relation types
- Gold label: ordered_nodes, ordered_edges, relation_type for each edge,
  chain_complete flag, expected_uncertainties

**Chain Types:**
1. frontend_request -> backend_api (REQUESTS_API)
2. backend_api -> controller_method (DEFINES_API)
3. controller -> service_method (CALLS_METHOD)
4. 1-hop chains
5. 2-hop chains
6. Unmatched frontend request (should report uncertainty)
7. Unresolved dynamic request (should report uncertainty)
8. Ambiguous calls (should not construct relation)

**Metrics:**
- Node precision / recall
- Edge precision / recall
- Exact chain match (all nodes and edges correct, in order)
- Partial chain coverage (fraction of gold chain recovered)
- Unsupported edge rate (edges not backed by stored relations)
- Rejection accuracy (correctly refusing to build unsupported edges)

### 3.D Generated Answer and Citation

**Goal:** Measure answer factual accuracy and citation quality.

**Test Design:**
- Input: question, project_id, gold fact units
- Output: answer text, references, uncertainties
- Gold label: required_claims, optional_claims, forbidden_claims,
  required_evidence, expected_language, answerable flag

**Metrics:**
- Required claim coverage (fraction of required_claims present in answer)
- Unsupported claim rate (claims not backed by any reference)
- Citation precision (fraction of cited references that are relevant)
- Citation recall (fraction of gold evidence that is cited)
- Path validity (all cited file paths exist in the repo at the fixed commit)
- Line-range validity (all cited line ranges contain the claimed code)
- Language compliance (answer language matches question language)
- Hallucination rate (fraction of answers containing forbidden_claims)
- Correct refusal rate (correctly stating "insufficient evidence")
- Incorrect refusal rate (refusing when evidence exists)

**LLM Judge Protocol (auxiliary only):**
- Fixed model and version, recorded in results
- Judge prompt saved alongside results
- System name hidden from judge
- Candidate order randomized
- 10% of samples judged twice for disagreement reporting
- Judge results never modify gold evidence

### 3.E Change Plan

**Goal:** Measure whether change plans identify the correct files and risks.

Change plan evaluation uses two complementary case types to balance objectivity
and coverage.

#### 3.E.1 Type A -- Historical-Change Cases (target: 6 of 12)

These cases are grounded in real repository commit history, providing an
objective, reproducible gold standard.

**Selection criteria:**
- Selected from real repository commit history
- The commit message or linked issue expresses a clear change intent (feature,
  fix, refactor)
- The parent commit is the "analyzed version" (the codebase the system sees)
- The target commit's actual diff = `observed_changed_files` (the objective
  ground truth)

**Exclusion criteria:**
- Formatting-only commits (whitespace, import reordering)
- Bulk rename or move commits with no semantic change
- Dependency lock-file updates (e.g., `package-lock.json`, `pom.xml` version bumps
  with no code change)

**Recorded fields per case:**
- `base_commit_sha`: the parent commit (analyzed version)
- `target_commit_sha`: the commit that implements the change
- `change_request`: natural language description of the intended change (derived
  from commit message / issue, not from the diff)
- `observed_changed_files`: files actually changed in the target commit (from diff)
- `source_commit_message`: original commit message text
- `diff_summary`: summarized diff stats (files changed, insertions, deletions)

**Metrics (named to reflect their nature):**
- "Historical changed-file recall" (not "absolute correctness"): fraction of
  `observed_changed_files` that the system recommended
- "Unsupported recommendation rate": fraction of system-recommended files with
  no support in the commit diff or stored graph evidence
- "Extra recommendation rate": fraction of system-recommended files beyond the
  observed set (may be reasonable but unverified)
- Risk coverage (fraction of required_risks mentioned)
- Forbidden recommendation rate
- Over-diffusion rate (recommending files far from the change scope)

**Fallback:** If 6 suitable historical commits cannot be found in the pilot
repository, reduce the Type A count and report the gap explicitly. Do not
lower the selection bar to fill the quota.

#### 3.E.2 Type B -- Expert-Annotated Hypothetical Cases (target: 6 of 12)

These cases cover change scenarios that may not exist in recent commit history
(e.g., cross-module refactoring, API versioning, framework migration).

**Annotation process:**
- An independent annotator proposes the change request and reads the code
- A separate reviewer independently reviews the annotation
- Disagreements between annotator and reviewer are marked as `needs_review`
  and resolved before the case enters the dataset

**File categories per case:**
- `must_change`: files that must be modified for the change to be functionally
  correct
- `likely_change`: files that a reasonable implementation would probably touch
- `context_only`: files needed for understanding but not modification
- `should_not_change`: files that a naive approach might recommend but should
  be left alone

**Constraints:**
- Cases are NOT called "human gold" without explicit human confirmation
- Disagreements are recorded, not silently resolved
- `needs_review` cases do not enter formal metrics until resolved

**Metrics:**
- Must-change file recall
- Recommended file precision
- Unsupported affected-file rate
- Risk coverage (fraction of required_risks mentioned)
- Forbidden recommendation rate
- Over-diffusion rate
- Miss rate (failing to recommend must-change files)

---

## 4. Repository Selection

### 4.1 Selection Criteria

1. Open-source license permitting local analysis (MIT, Apache-2.0, BSD, ISC)
2. Recorded metadata: repo_id, name, URL, license, commit_sha, default_branch,
   primary language, framework, file_count, line_count, parseable_entity_count
3. Java/Vue repos should contain: Spring controllers, services, frontend
   Axios/fetch wrappers, real API routes, multi-file call chains
4. Diversity requirements: monolith, frontend-backend separation, dynamic
   requests, dependency injection, overloaded methods
5. Not toy projects (minimum ~50 source files)
6. Pilot: not oversized (maximum ~500 source files)
7. Data split by repository, not by question

### 4.2 Pilot Repository Candidates

The authoritative candidate list is in `repos/manifest.yaml`. The SPEC does
not duplicate this list to prevent drift between the SPEC and the manifest.

**Summary of candidates in the manifest:**

- **RuoYi-Vue** (MIT): Spring Boot + Vue 2 admin system. Selected for the Pilot
  due to its manageable size, clear structure, and permissive license.
- **JeecgBoot** (Apache-2.0): Spring Boot + Vue 3 platform. Extended candidate
  for the multi-repository expansion phase.
- **Pig** (MIT): Spring Cloud + Vue 3 microservice platform. Extended candidate
  for the multi-repository expansion phase.
- **Halo** (GPL-3.0): Spring Boot + Vue 3 blog platform. Boundary candidate
  only -- its GPL-3.0 license is more restrictive than the permissive-license
  preference in the selection criteria. It is included for diversity analysis
  but is NOT claimed as a permissive-license project.
- **Python project** (TBD): To be selected for the extended phase, providing
  language diversity beyond Java/Vue.

All unverified data (file counts, line counts, entity estimates) is marked as
such in the manifest. File counts are measured after clone, not estimated from
repository metadata.

### 4.3 Data Split Strategy

| Split | Repositories | Purpose |
|-------|-------------|---------|
| development | 2-3 repos | Design questions, tune metrics, debug runners |
| validation | 1 repo | Validate final metrics before reporting |
| holdout | 1 repo | Never used until final benchmark report |

Pilot uses a single repository in the development split.

---

## 5. Special Sample Design

Each repository must include the following difficulty samples (Section 7 in the
task prompt). These are categorized into 20 types:

1. Same-name classes / methods / overloads
2. Similar but unrelated files
3. Partial string match between frontend URL and backend API
4. Dynamic URLs, template strings, variable concatenation
5. Axios/request wrapper patterns
6. Spring class-level + method-level path composition
7. Path parameters (`/api/users/{id}`)
8. HTTP method mismatch (GET vs POST to same path)
9. Unmatched frontend request (no backend API)
10. Reflection, proxy, inheritance, dynamic dispatch
11. Runtime facts not provable by static analysis
12. Questions with false premises
13. Non-existent implementations
14. Questions requiring "I'm not sure" responses
15. Keyword-search-advantaged questions
16. Semantic-search-advantaged questions
17. GraphRAG-advantaged questions
18. GraphRAG-noise questions
19. Chinese rewrite-advantaged queries
20. Chinese rewrite专有名词 loss queries

**Difficulty levels:**
- easy: Contains explicit symbols, paths, or API names
- medium: Natural language function description
- hard: Cross-file, cross-layer, distractors, or uncertainty judgment required

**Minimum composition per repository:**
- At least 20% should be unanswerable / should-refuse / insufficient-evidence
- At least 30% should be hard
- Both Chinese and English must be covered
- Questions must NOT leak class/method names into the question text for hard samples

---

## 6. Baselines and Ablation

### 6.1 Baselines

| ID | Method | External Dependencies | Notes |
|----|--------|----------------------|-------|
| B0 | ripgrep / text search | None | Lowest complexity reference |
| B1 | SQLite keyword search | None (uses indexed DB) | Field-weighted SQL LIKE |
| B2 | Vector search only | Embedding API | Qdrant cosine similarity |
| B3 | Hybrid search | Embedding API | 0.7V + 0.3K fusion |
| B4 | Hybrid + Graph expansion | Embedding API + Graph DB | GraphRAG retriever |
| B5 | Full Agent workflow | Embedding API + LLM + Graph | End-to-end pipeline |

### 6.2 Ablation Experiments

| ID | Variation | What It Tests |
|----|-----------|--------------|
| A1 | B3 without query rewrite | Value of Chinese rewriting |
| A2 | B3 with 0.5/0.5 weights | Weight sensitivity |
| A3 | B3 with 0.3/0.7 weights | Keyword-dominant fusion |
| A4 | B3 with RRF (Reciprocal Rank Fusion) | Fusion method comparison |
| A5 | B4 with depth=0 | No graph expansion |
| A6 | B4 with depth=1 | Shallow graph expansion |
| A7 | B5 without conversation memory | Value of multi-turn context |
| A8 | B5 without evidence validation | Value of evidence guard |
| A9 | B5 without repair loop | Value of repair mechanism |

### 6.3 Fairness Rules

- All methods use identical questions
- All methods use identical repository commit
- All methods use identical top_k (unless the method inherently differs)
- Record whether each method requires external models
- Separate indexing time from query time
- Distinguish cold-start from warm queries
- No baseline may access gold information that others cannot
- All failures are counted in results

---

## 7. Data Format

### 7.1 Schema Location

The JSON Schema is at `evaluation/schema/evaluation_case.schema.json`.

### 7.2 Key Fields

Each evaluation case contains:

- **Identity:** dataset_version, question_id, repo_id, commit_sha, split
- **Question:** task_type, language, difficulty, question text, answerable flag,
  question_origin
- **Gold Standard:** gold_status (machine_proposed | machine_verified | human_verified),
  gold_entities, gold_files, gold_nodes, gold_edges, required_claims,
  optional_claims, forbidden_claims, acceptable_alternatives,
  expected_uncertainties
- **Annotation Metadata:** annotator, reviewer, review_status, notes
- **Provenance:** source_files, source_lines, generation_method, timestamps

**Note on `required_claims` evidence format:** Each claim in `required_claims`
uses `evidence_ranges` -- an array of `{file_path, start_line, end_line}` objects
-- rather than `evidence_lines` (a flat integer array). This preserves line-range
context so that validators can verify the evidence block contains the claimed
code, not just that the line number exists.

### 7.3 Split Integrity

- Splits are by repository, not by random question assignment
- No question from a holdout repository may appear in development or validation
- Schema validation includes a split-leakage check

### 7.4 Internal Fixture Provenance

`sample-project` is an internal test fixture at
`backend/tests/fixtures/sample_project/`. It does not have an independent Git
commit. For evaluation purposes, it uses the parent ResearchCode-Agent
repository's commit SHA combined with
`repository_subdir: backend/tests/fixtures/sample_project`.

Usage constraints:
- It is used ONLY for framework smoke tests (runner integration, schema
  validation, pipeline wiring).
- It NEVER enters real benchmark metrics.
- No commit SHA is fabricated.

### 7.5 Stable Entity Key

Database auto-increment `entity_id` is NOT stable across rescans. Gold labels
use `stable_entity_key`, defined as the SHA-256 of the normalized concatenation:

```
repo_id|commit_sha|relative_file_path|entity_type|qualified_name|start_line|end_line
```

Normalization rules:
- File paths use POSIX separators (forward slashes)
- File paths are lowercased
- Fields are joined with `|` (pipe character)
- No trailing whitespace or newline before hashing

The implementation lives in `scripts/stable_entity_key.py`.

`gold_nodes` and `gold_edges` reference `stable_entity_key`. Database `entity_id`
is recorded only as `runtime_entity_id` for a specific scan run, enabling
traceability without coupling gold labels to volatile auto-increment IDs.

---

## 8. Performance, Cost, and Reliability

### 8.1 Recorded Metrics

For each baseline and the full system:

- Scan: file count, entity count, relation count, scan duration
- Vector build: chunk count, embedding API calls, build duration, collection size
- Query: p50/p95 latency, LLM call count, embedding call count, query rewrite
  call count, input/output tokens, estimated cost
- Reliability: degradation count, zero-result count, provider failure count,
  evidence repair count, guarded failure count

### 8.2 Environment Record

Every report must include:

- OS, CPU, RAM
- Python/Node versions
- Embedding provider/model
- LLM provider/model
- Qdrant mode (local memory / remote)
- Configuration parameters
- Dataset version
- Repository commit SHA
- Run timestamp

If real token counts or costs are unavailable, they are marked "unavailable",
never estimated.

---

## 9. Quality Gates

### 9.1 machine_proposed -> machine_verified

A sample advances to machine_verified only when ALL of the following pass:

1. JSON Schema validation passes
2. repo_id and commit_sha are valid and the repo is accessible
3. All gold files exist at the specified commit
4. All line ranges are valid and contain the annotated text
5. All entities and relations have traceable provenance
6. Question Generator and Evidence Annotator are different agents. Enforced by
   semantic validation in `validate_dataset.py`, not by JSON Schema (Draft-07
   cannot express cross-field inequality).
7. Adversarial Reviewer has completed review
8. No unresolved severe disagreements
9. Question does not leak non-trivial answers
10. answerable label has explicit justification
11. forbidden_claims and uncertainty requirements reviewed
12. No cross-split data leakage

### 9.2 machine_verified -> human_verified

Before advancing to human_verified:

- Human reviewer must spot-check ALL hard samples
- Human reviewer must spot-check 10-20% of easy/medium samples
- Systematic errors trigger expanded review and retroactive correction

Until human review occurs, the dataset remains at machine_verified and the
report explicitly states this limitation.

### 9.3 Semantic Validation Rules

Beyond JSON Schema structural checks, `validate_dataset.py` enforces the
following semantic rules. A sample fails validation if any applicable rule
is violated:

1. **Task-specific gold requirements:** `machine_verified` samples must satisfy
   the gold requirements for their task type (e.g., TRACE_CHAIN needs
   gold_nodes and gold_edges; CODE_QA needs gold_entities or gold_files).
2. **Retrieval entity coverage:** Retrieval-layer samples must have at least
   one `must_recall` entity OR `answerable=false`.
3. **Trace chain completeness:** `trace_chain` samples with `answerable=true`
   must have `gold_nodes` and `gold_edges`, unless the sample is explicitly
   marked as `partial` or `unresolved`.
4. **Change plan evidence:** `change_plan` samples must have either historical
   change evidence (Type A, Section 3.E.1) or reviewed file classification
   (Type B, Section 3.E.2).
5. **Unanswerable justification:** Samples with `answerable=false` must provide
   `expected_uncertainties` or a refusal justification.
6. **Line range validity:** `start_line <= end_line` for all ranges in all
   evidence fields.
7. **Edge endpoint existence:** Every `gold_edge` source and target must exist
   in `gold_nodes`.
8. **Provenance coverage:** `provenance.source_files` must cover all files
   referenced in gold evidence (gold_nodes, gold_edges, evidence_ranges).
9. **Annotator-reviewer separation:** `annotator` and `reviewer` must not be
   identical. Enforced by `validate_dataset.py`, not by JSON Schema.
10. **Status-metric exclusion:** Samples with `review_status` of `rejected` or
    `needs_review` must not enter formal metrics.
11. **Split fingerprint uniqueness:** `development`, `validation`, and `holdout`
    splits must not share identical question fingerprints (normalized question
    text hash).

---

## 10. Stage Plan

| Stage | Description | Status |
|-------|-------------|--------|
| 0 | Project Investigation | Complete |
| 1 | Evaluation Design | Complete (awaiting approval) |
| 2 | Pilot Dataset (36 questions, 1 repo) | Pending |
| 3 | Pilot Report | Pending |
| 4 | Extended Dataset (3-5 repos, 150-300 questions) | Pending |
| 5 | Full Benchmark | Pending |
| 6 | Interview and Long-term Reports | Pending |

### 10.1 Checkpoint 1 (Current)

Present to user:
1. Located project root: `F:\LIUQINGYUN\ResearchCode_Agent`
2. Files to be created: `evaluation/` directory tree (see README.md)
3. Candidate repositories (Section 4.2, manifest at `repos/manifest.yaml`)
4. Pilot scope: 36 questions, distribution below
5. Required resources: network (repo download), disk (~200MB), no paid API for
   offline baselines
6. Key risks (Section 11)
7. Awaiting user approval

### 10.2 Pilot Task Distribution (36 Questions)

The Pilot consists of exactly 36 questions. The dimensions below are
**cross-cutting**, not additive -- each question belongs to exactly one cell
in each dimension simultaneously.

**By Task Type:**

| Task Type | Count |
|-----------|-------|
| CODE_QA | 12 |
| TRACE_CHAIN | 12 |
| CHANGE_PLAN | 12 |
| **Total** | **36** |

**By Language:**

| Language | Count |
|----------|-------|
| zh (Chinese) | 18 |
| en (English) | 18 |
| **Total** | **36** |

**By Difficulty:**

| Difficulty | Count |
|------------|-------|
| easy | 8 |
| medium | 16 |
| hard | 12 |
| **Total** | **36** |

**By Answerability:**

| Answerability | Count |
|---------------|-------|
| answerable | 27 |
| unanswerable | 9 |
| **Total** | **36** |

**Important notes:**
- These dimensions are cross-cutting, NOT additive. A single question is, for
  example, simultaneously CODE_QA + zh + medium + answerable.
- Answer/Citation (Layer D) is evaluated on the same 36 questions with
  additional gold fact-unit annotations. It is not a separate question set.
- Routing (Layer A) is evaluated on all 36 questions.
- Each question has exactly one `expected task_type`.

---

## 11. Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| External repo unavailable or license changes | Medium | Record multiple candidates; fix commit SHA immediately after clone |
| LLM answer non-deterministic across runs | High | temperature=0 reduces but does not guarantee determinism. Record provider, model, model version (when available), temperature, seed (when supported), timestamp, and raw response. Full benchmark runs each question once by default; a fixed stability subset (20% of Pilot) runs 3x to measure variance. |
| Embedding API cost for large repos | Medium | Pilot uses 1 medium repo; estimate cost before full run |
| Static parser misses dynamic patterns | Expected | These are intentional test cases (special samples 10-11) |
| Gold annotation errors | High | Adversarial reviewer + deterministic validator + human spot-check |
| Agent self-grading bias | Critical | Strict role separation; generator != annotator != reviewer |
| Over-fitting to pilot repo | Medium | Holdout repo never used for tuning; multi-repo expansion planned |
| Insufficient hard samples | Medium | Explicit construction of all 20 difficulty types per repo |
| Keyword search baseline unfair (no semantic understanding) | Low | This is intentional; B0 measures "what grep can do" |
| Qdrant unavailability during benchmark | Medium | Record as failure; B0/B1 do not need Qdrant |

---

## 12. Interview Evidence Questions (Preview)

The final `interview-evidence.md` will answer these with real data:

1. Why not grep? -> B0 vs B3 recall comparison on hard queries
2. Why not pure vector? -> B2 vs B3 on exact-symbol and synonym queries
3. Why not plain RAG? -> B3 vs B5 on citation quality and hallucination rate
4. What did GraphRAG improve? -> B3 vs B4 on trace chain completeness
5. What did GraphRAG NOT improve? -> Cases where graph adds noise
6. Why SQLite over Neo4j? -> Scale analysis, latency comparison, maintenance cost
7. Why deterministic planner? -> Routing accuracy, latency, predictability
8. What are the Agent's capability boundaries? -> Failure catalog summary
9. What questions should the system refuse? -> Unanswerable sample results
10. Maximum validated repository size? -> Performance data from largest test repo
11. Biggest productionization gap? -> Limitations list vs evaluation findings
12. What does the next optimization step target? -> Metric-driven recommendations
