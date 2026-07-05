# Week 3 GraphRAG and API Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight, project-scoped code graph that traces frontend requests through backend APIs and controller methods to statically observed service calls, expose deterministic graph-query APIs, enrich retrieval with one- or two-hop graph context, and display the resulting chain in a minimal Vue 3/Cytoscape page.

**Architecture:** SQLite remains both the durable entity store and the lightweight graph store; no graph database is introduced. Existing `CodeEntity` rows are graph nodes and `CodeRelation` rows are directed edges. Java parsing records injection and invocation evidence, the cross-file relation builder resolves that evidence into conservative `CALLS_METHOD` edges, and `GraphQueryService` performs bounded BFS with project and relation-type filters. GraphRAG starts with the existing hybrid search and adds ranked graph neighbors without changing Week 2 retrieval. The trace agent receives structured graph evidence and uses the existing injectable LLM client; automated tests always use fakes.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Pydantic 2, tree-sitter Java parsing, SQLite, existing Qdrant/hybrid retrieval, Vue 3, TypeScript, Vite, Cytoscape.js, Vitest, pytest, pytest-cov.

---

## Scope, baseline, and execution rules

- Week 3 implements Day 15 through Day 21 from `plan.md`.
- Day 15 is mostly a baseline verification task: Week 1 already creates `DEFINES_API`, `CONTAINS`, and `REQUESTS_API` edges and enforces entity/edge uniqueness.
- Do not add Neo4j, NetworkX, a second graph store, authentication, long-term memory, a general planner, code modification planning, or a unified chat UI. Those are absent from the MVP or belong to Week 4.
- Continue TDD for every backend and frontend behavior: focused failing test, minimal implementation, focused pass, then regression suite.
- Static analysis must be honest. Create `CALLS_METHOD` only when source code contains a matching invocation; do not infer calls merely because a controller and service have semantically related names.
- Exact injection/type resolution has confidence `0.8`. A unique project-scoped method-name resolution without type evidence may use `0.6`. Ambiguous candidates produce no edge.
- Every database query and edge traversal must be constrained by `project_id`.
- BFS defaults to one hop, allows at most two hops for public endpoints, deduplicates nodes/edges, and has deterministic ordering.
- Graph expansion never changes the existing hybrid-search score. It creates separate graph-aware results containing `retrieval_score`, `graph_depth`, and `relation_reason`.
- Real embedding/LLM calls are not allowed in automated tests. Use fake embedders, in-memory Qdrant, and fake LLM clients. Perform at most one manually approved real trace-LLM smoke test after all offline tests pass.
- Preserve synchronous service/API style used by Week 1 and Week 2.
- After each task, run the focused tests. Before any commit, run the full backend suite and the relevant frontend checks.

## Current baseline to preserve

| Capability | Current status | Week 3 treatment |
| --- | --- | --- |
| `backend_api -> java_method` via `DEFINES_API` | Implemented | Lock with regression tests |
| `java_class -> java_method` via `CONTAINS` | Implemented | Lock with regression tests |
| `frontend_api_call -> backend_api` via `REQUESTS_API` | Implemented | Reuse as first chain hop |
| Entity and relation uniqueness | Database constraints + scan replacement | Verify rescan remains duplicate-free |
| Hybrid search | Implemented | Inject into search-chain and GraphRAG |
| Cited RAG context and LLM client | Implemented | Reuse; do not fork another LLM stack |
| Frontend application | Not created | Create the minimum Week 3 graph UI only |

## Target graph semantics

```text
frontend_api_call
  ──REQUESTS_API──> backend_api
  ──DEFINES_API──> java_method (Controller handler)
  ──CALLS_METHOD──> java_method (Service method)

java_class
  ──CONTAINS──> java_method
```

Edge direction is evidence direction. Traversal may optionally inspect incoming and outgoing edges, but serialized edges retain their stored `source_id` and `target_id`.

## File map

| Path | Responsibility |
| --- | --- |
| `backend/app/parsers/java_parser.py` | Extract injected dependency evidence and qualified method invocations |
| `backend/app/parsers/relation_builder.py` | Resolve invocation evidence into conservative cross-file `CALLS_METHOD` edges |
| `backend/app/graph/types.py` | Internal immutable graph node/edge/result contracts |
| `backend/app/graph/query_service.py` | Project-scoped bounded BFS and exact API-chain lookup |
| `backend/app/rag/graph_retriever.py` | Hybrid search followed by ranked one/two-hop expansion |
| `backend/app/rag/graph_context_builder.py` | Deterministic, bounded trace context for the LLM |
| `backend/app/services/trace_service.py` | GraphRAG → trace context → grounded LLM answer orchestration |
| `backend/app/schemas/graph.py` | BFS, exact chain, and natural-language chain HTTP contracts |
| `backend/app/schemas/agent.py` | Add trace request/response contracts |
| `backend/app/api/graph_api.py` | `/api/graph/api-chain` and `/api/graph/search-chain` |
| `backend/app/api/agent_api.py` | Add `/api/agent/trace` |
| `backend/app/core/dependencies.py` | Cached graph service/retriever factories and test seams |
| `backend/app/main.py` | Register the graph router |
| `frontend/` | Minimal Vue 3/TypeScript/Vite graph viewer |

---

### Task 1: Lock the Week 1 graph baseline (Day 15)

**Files:**
- Modify: `backend/tests/unit/test_java_parser.py`
- Modify: `backend/tests/unit/test_relation_builder.py`
- Modify: `backend/tests/integration/test_scan_service.py`

- [x] **Step 1: Add parser regression assertions**

Assert that a controller fixture produces exactly one `DEFINES_API` edge per API mapping and one `CONTAINS` edge per method, and that backend API metadata includes `controller_class`, `handler_method`, `http_method`, `path`, and `normalized_path`.

- [x] **Step 2: Add relation-builder regression assertions**

Assert that exact normalized method/path matches create one `REQUESTS_API` edge and repeated candidate input cannot create duplicate `(source_key, target_key, relation_type)` edges.

- [x] **Step 3: Add rescan integration coverage**

Scan the same fixture project twice. Assert unchanged entity/relation counts and no duplicate entity keys or graph edges after the second scan.

- [x] **Step 4: Run the focused baseline tests**

Run from `backend`:

```cmd
.venv\python.exe -m pytest tests\unit\test_java_parser.py tests\unit\test_relation_builder.py tests\integration\test_scan_service.py
```

Expected: all tests pass without production changes unless a real regression is discovered.

---

### Task 2: Extract Java dependency and invocation evidence (Day 16, parser half)

**Files:**
- Modify: `backend/app/parsers/java_parser.py`
- Modify: `backend/tests/fixtures/sample_project/backend/src/AlertController.java`
- Modify: `backend/tests/unit/test_java_parser.py`

- [x] **Step 1: Strengthen the Java fixture**

Change the sample controller to demonstrate constructor injection and an actual invocation:

```java
@RestController
@RequestMapping("/api/alerts")
class AlertController {
    private final AlertService alertService;

    AlertController(AlertService alertService) {
        this.alertService = alertService;
    }

    @GetMapping("/{id}")
    Alert getAlert(Long id) {
        return alertService.findById(id);
    }
}
```

Keep a second method/API in the fixture so multi-endpoint behavior remains covered.

- [x] **Step 2: Write failing extraction tests**

Cover:

- field injection through `@Autowired`;
- field injection through `@Resource`;
- constructor injection assigned with `this.alertService = alertService`;
- invocation extraction for `alertService.findById(...)`;
- no false invocation for a bare local call such as `validate(id)`;
- nested classes keep their own dependency evidence.

Expected method metadata:

```python
{
    "declaring_class": "AlertController",
    "invocations": [
        {
            "qualifier": "alertService",
            "method": "findById",
            "receiver_type": "AlertService",
        }
    ],
}
```

- [x] **Step 3: Implement tree-sitter evidence extraction**

Use Java syntax nodes, not whole-file regexes, to collect class fields, constructor parameters/assignments, and method-invocation receiver/method names. Store only JSON-safe evidence in entity metadata. Do not emit cross-file relations from the parser because the target service entity may be parsed later.

- [x] **Step 4: Run parser tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_java_parser.py
```

Expected: parser tests pass and existing API extraction remains unchanged.

---

### Task 3: Resolve `CALLS_METHOD` relations conservatively (Day 16, graph half)

**Files:**
- Modify: `backend/app/parsers/relation_builder.py`
- Modify: `backend/tests/unit/test_relation_builder.py`
- Modify: `backend/tests/integration/test_scan_api.py`

- [x] **Step 1: Write failing relation-resolution tests**

Build in-memory candidates representing controller methods and service methods. Cover:

- receiver type `AlertService` + method `findById` resolves to `AlertService.findById` at confidence `0.8`;
- a unique method-name-only match resolves at confidence `0.6`;
- multiple services exposing the same method without receiver type produce no edge;
- non-service classes are not selected as service targets;
- duplicate invocation evidence produces one edge;
- candidates from the same scan can resolve across different files.

- [x] **Step 2: Implement project-scan-level resolution**

Index Java classes by qualified/simple name and Java methods by `(declaring_class, method_name)`. Use class metadata `is_service` to limit targets. Emit:

```python
RelationCandidate(
    source_key=controller_method.local_key,
    target_key=service_method.local_key,
    relation_type="CALLS_METHOD",
    confidence=0.8,
    metadata={
        "qualifier": "alertService",
        "resolution": "receiver_type",
    },
)
```

Fall back to confidence `0.6` only for a single unambiguous service method candidate.

- [x] **Step 3: Verify persisted relations through the scan API**

Scan the sample project and assert the persisted chain contains:

```text
AlertView request
  -> GET /api/alerts/{id}
  -> AlertController.getAlert
  -> AlertService.findById
```

- [x] **Step 4: Run focused parser/scan tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_java_parser.py tests\unit\test_relation_builder.py tests\integration\test_scan_api.py
```

Expected: the new `CALLS_METHOD` relation is persisted with `0.8` confidence.

---

### Task 4: Implement graph contracts and bounded BFS (Day 17)

**Files:**
- Create: `backend/app/graph/__init__.py`
- Create: `backend/app/graph/types.py`
- Create: `backend/app/graph/query_service.py`
- Create: `backend/tests/unit/test_graph_query_service.py`

- [ ] **Step 1: Define immutable internal contracts**

Create `GraphNode`, `GraphEdge`, and `GraphResult`. A node contains `entity_id`, `label`, `entity_type`, `qualified_name`, `file_path`, `start_line`, `end_line`, and `content`. An edge contains `relation_id`, `source_id`, `target_id`, `relation_type`, `confidence`, and parsed metadata. `GraphResult` contains tuples of nodes and edges.

- [ ] **Step 2: Write failing BFS tests**

Using SQLite test rows, cover:

- depth `0` returns only the seed;
- depth `1` and `2` return bounded neighbors;
- traversal sees both incoming and outgoing edges;
- `relation_types` filters expansion;
- another project's nodes and edges never leak;
- cycles terminate and duplicate edges/nodes are removed;
- nonexistent seed returns `ENTITY_NOT_FOUND`;
- invalid depth outside `0..2` is rejected by the public schema.

- [ ] **Step 3: Implement deterministic BFS**

Fetch adjacency in bounded batches, maintain `visited_node_ids` and `seen_edge_ids`, and sort output by `(depth, entity_id)` for nodes and `(source_id, target_id, relation_type, relation_id)` for edges.

- [ ] **Step 4: Add exact API-chain lookup**

Add `find_api_chain(project_id, method, api_path)`:

1. uppercase the method;
2. normalize the path with the existing `normalize_api_path`;
3. locate matching `backend_api` nodes from metadata;
4. include incoming `REQUESTS_API`;
5. include outgoing `DEFINES_API`;
6. from handler methods include outgoing `CALLS_METHOD`;
7. return deterministic nodes/edges;
8. return `API_NOT_FOUND` with 404 if no backend API matches.

- [ ] **Step 5: Run graph service tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_graph_query_service.py
```

---

### Task 5: Expose exact and natural-language graph APIs (Day 18)

**Files:**
- Create: `backend/app/schemas/graph.py`
- Create: `backend/app/api/graph_api.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/core/dependencies.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_graph_api.py`

- [ ] **Step 1: Define stable HTTP schemas**

Create:

- `GraphNodeRead`;
- `GraphEdgeRead`;
- `GraphResponse` with `nodes`, `edges`, and `references`;
- `SearchChainRequest` with `project_id`, nonblank `query`, `limit=5` constrained to `1..20`, and `max_depth=2` constrained to `1..2`.

References must contain file path and line range and be deduplicated by entity ID.

- [ ] **Step 2: Write exact API-chain endpoint tests**

Test:

```http
GET /api/graph/api-chain?project_id=1&method=GET&api_path=/api/alerts/123
```

Assert the response contains frontend request, backend API, controller handler, and observed service method, plus the three edge types. Also test 404, invalid query parameters, and project isolation.

- [ ] **Step 3: Implement and register `graph_router`**

Mount the router under `/api/graph`. Build `GraphQueryService` from the request-scoped database session. Do not cache a SQLAlchemy session globally.

- [ ] **Step 4: Write natural-language search-chain endpoint tests**

Override the hybrid-search dependency with a fake returning known seed hits. Assert `/api/graph/search-chain` expands each seed with BFS, merges graphs, deduplicates nodes/edges, and never calls a real embedding model or Qdrant.

- [ ] **Step 5: Implement search-chain orchestration**

Run existing hybrid search, treat ranked hits as seeds, expand each up to `max_depth`, and merge results. Seed ordering follows retrieval rank; remaining graph nodes follow depth then entity ID.

- [ ] **Step 6: Run graph API tests**

```cmd
.venv\python.exe -m pytest tests\integration\test_graph_api.py
```

---

### Task 6: Implement the GraphRAG retriever (Day 19)

**Files:**
- Create: `backend/app/rag/graph_retriever.py`
- Create: `backend/tests/unit/test_graph_retriever.py`

- [ ] **Step 1: Define graph-aware retrieval records**

Each result contains the original entity payload plus:

- `retrieval_score`: hybrid score for direct hits, otherwise inherited seed score;
- `graph_depth`: `0`, `1`, or `2`;
- `relation_reason`: `direct hybrid-search hit` or a concrete explanation such as `AlertController.getAlert CALLS_METHOD AlertService.findById`;
- `seed_entity_id`: the direct hit that introduced the neighbor.

- [ ] **Step 2: Write failing ranking/deduplication tests**

Cover:

- direct hits precede one-hop nodes, which precede two-hop nodes;
- within equal depth, higher inherited score wins;
- the same entity reached from multiple seeds appears once;
- direct-hit information replaces graph-neighbor information for the same entity;
- relation filters prevent unrelated `CONTAINS` expansion when requested;
- expansion respects result and depth limits.

- [ ] **Step 3: Implement `GraphRagRetriever`**

Inject a `HybridSearchService`-compatible search object and `GraphQueryService`. Do not subclass or modify Week 2 hybrid ranking. Use relation types:

```python
("REQUESTS_API", "DEFINES_API", "CALLS_METHOD")
```

for chain retrieval by default.

- [ ] **Step 4: Run GraphRAG tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_graph_retriever.py
```

---

### Task 7: Build bounded trace context and the trace API (Day 21 backend)

**Files:**
- Create: `backend/app/rag/graph_context_builder.py`
- Create: `backend/app/services/trace_service.py`
- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/api/agent_api.py`
- Modify: `backend/app/core/dependencies.py`
- Create: `backend/tests/unit/test_graph_context_builder.py`
- Create: `backend/tests/unit/test_trace_service.py`
- Create: `backend/tests/integration/test_trace_api.py`

- [ ] **Step 1: Write graph-context tests**

Require deterministic citation numbering, a configurable total character budget, explicit edge evidence, retained file/line references, and omission of unrelated nodes when the budget is reached.

- [ ] **Step 2: Implement `GraphContextBuilder`**

Format compact evidence blocks containing node citation, qualified name, file/lines, relevant code, graph depth/reason, and stored edges. Never synthesize an edge that is absent from `CodeRelation`.

- [ ] **Step 3: Define trace contracts**

`TraceRequest` contains `project_id`, nonblank `question`, `limit=5`, and `max_depth=2`. `TraceResponse` contains:

- `answer`;
- `references`;
- `graph_nodes`;
- `graph_edges`;
- `uncertainties`.

- [ ] **Step 4: Write trace-service tests with a fake LLM**

Assert:

- GraphRAG results feed the prompt;
- the system prompt requires chain, involved files, and uncertain/missing links;
- stored edge evidence is clearly separated from inferred explanation;
- no hits return a deterministic no-support answer without invoking the LLM;
- references and graph data are returned unchanged;
- fake-LLM failure follows the existing domain-error policy.

- [ ] **Step 5: Implement grounded trace orchestration**

Reuse `LlmClient`. The prompt must prohibit claiming controller-to-service calls unless a `CALLS_METHOD` edge or explicit code snippet supports the claim. It must ask the model to label missing segments as “cannot be determined from indexed code.”

- [ ] **Step 6: Add `POST /api/agent/trace`**

Wire dependencies with override-friendly factories. Automated endpoint tests inject fake search/graph/LLM components and consume zero paid tokens.

- [ ] **Step 7: Run trace tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_graph_context_builder.py tests\unit\test_trace_service.py tests\integration\test_trace_api.py
```

---

### Task 8: Create the minimal Vue graph application (Day 20)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/env.d.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/api/graph.ts`
- Create: `frontend/src/types/graph.ts`
- Create: `frontend/src/components/GraphPanel.vue`
- Create: `frontend/src/views/GraphView.vue`
- Create: `frontend/src/components/__tests__/GraphPanel.spec.ts`
- Create: `frontend/src/views/__tests__/GraphView.spec.ts`

- [ ] **Step 1: Scaffold only the required frontend**

Use Vue 3, TypeScript, Vite, Axios, Cytoscape.js, Vitest, Vue Test Utils, and jsdom. Do not add router, state management, authentication, general chat, project management, or Element Plus yet.

- [ ] **Step 2: Define API and UI contracts**

Mirror `GraphResponse` in TypeScript. `searchChain()` calls `POST /api/graph/search-chain`; use a Vite development proxy from `/api` to `http://127.0.0.1:8000`.

- [ ] **Step 3: Write failing component tests**

Mock Cytoscape and the graph API. Cover:

- submit is disabled for blank query;
- loading, error, and empty states;
- successful response maps every node and edge into Cytoscape elements;
- selecting a node displays type, qualified name, file path, line range, and code snippet;
- a second search replaces the previous graph and destroys the old Cytoscape instance.

- [ ] **Step 4: Implement `GraphPanel.vue`**

Create Cytoscape only after the container exists. Style node colors by `entity_type`, label edges by `relation_type`, use a left-to-right layout, emit selected-node details, and destroy the instance on unmount.

- [ ] **Step 5: Implement `GraphView.vue`**

Provide project ID, query input, search button, graph canvas, legend, and node detail panel. Keep project ID explicit because project-selection UI belongs to Week 4 integration.

- [ ] **Step 6: Install and run frontend checks**

Network dependency installation requires user approval during execution:

```cmd
cd frontend
npm install
npm test -- --run
npm run build
```

Expected: component tests pass and TypeScript production build succeeds.

---

### Task 9: Offline Week 3 acceptance and documentation

**Files:**
- Create: `backend/tests/integration/test_week3_acceptance.py`
- Create: `backend/scripts/trace_api_chain.py`
- Modify: `backend/README.md`
- Modify: `.env.example`
- Modify: `.gitignore` only if frontend artifacts are not already covered

- [ ] **Step 1: Add an end-to-end offline acceptance test**

Using temporary SQLite, in-memory Qdrant/fake hybrid search where appropriate, and a fake LLM:

1. register the sample project;
2. scan/index it;
3. verify `REQUESTS_API`, `DEFINES_API`, and `CALLS_METHOD`;
4. query the exact API chain;
5. query a natural-language chain;
6. invoke trace service;
7. assert graph/reference consistency and no cross-project leakage.

- [ ] **Step 2: Add a CMD-friendly inspection script**

Support:

```cmd
.venv\python.exe -m scripts.trace_api_chain 1 GET /api/alerts/123
```

Print nodes in chain order, edges with confidence, file/line references, and missing segments. This script must not call an LLM.

- [ ] **Step 3: Document operation and limitations**

Explain backend endpoints, frontend startup, relation semantics, confidence levels, why static analysis can miss dynamic calls, how to run offline tests, and how to perform the optional paid trace test. Do not put a real API key in tracked files.

- [ ] **Step 4: Run complete offline verification**

From `backend`:

```cmd
.venv\python.exe -m pytest
.venv\python.exe -m pytest --cov=app --cov-report=term-missing
.venv\python.exe -m compileall -q app scripts tests
```

From `frontend`:

```cmd
npm test -- --run
npm run build
```

Expected: all suites pass, backend coverage remains at least 80%, compilation succeeds, and no real LLM/embedding request is made.

- [ ] **Step 5: User manual test gate**

Start the backend and frontend, then ask the user to verify:

1. searching `alert API` renders frontend → API → controller → service;
2. clicking each node shows the correct file and line range;
3. exact API-chain CMD output agrees with the UI;
4. unknown API/query gives a clear empty/not-found response;
5. one optional `/api/agent/trace` request returns a grounded explanation and graph data.

Do not commit or push until the user confirms this gate.

---

## Planned execution checkpoints

| Checkpoint | Tasks | User-visible result |
| --- | --- | --- |
| A | 1–3 | Scan creates an evidence-backed Controller → Service edge |
| B | 4–5 | Exact and natural-language graph APIs return nodes/edges |
| C | 6–7 | GraphRAG and grounded trace API work with fake/offline tests |
| D | 8 | Browser displays an interactive Cytoscape chain |
| E | 9 | Full offline suite and one user-controlled manual acceptance pass |

At each checkpoint, explain the concepts involved and provide a CMD command for manual inspection. Commit and push the isolated Week 3 branch only after the corresponding user approval; merging to `main` remains a separate, explicit action.

## Definition of done

- [ ] Existing Week 1/2 behavior remains green.
- [ ] Sample scan creates one honest `CALLS_METHOD` edge from controller handler to service method.
- [ ] Exact API lookup returns frontend request, backend API, handler, and observed service call.
- [ ] Natural-language search expands hybrid hits by at most two graph hops.
- [ ] GraphRAG results are deterministic, deduplicated, bounded, and explain why each neighbor was included.
- [ ] `/api/agent/trace` returns grounded text, references, graph nodes, graph edges, and uncertainty information.
- [ ] Vue/Cytoscape graph renders and node details match backend references.
- [ ] Backend full suite, coverage, compileall, frontend tests, and frontend build pass offline.
- [ ] No credentials, local database, Qdrant data, model cache, `.venv`, `node_modules`, or frontend build output are committed.
- [ ] User completes the manual test gate before branch commit/push.

## Self-audit against `plan.md`

- Day 15: preserved and regression-tested rather than reimplemented.
- Day 16: injection evidence, service invocation extraction, `CALLS_METHOD`, and `0.8/0.6` confidence are covered.
- Day 17: SQLite-backed BFS, exact API chain, and unified nodes/edges/references are covered.
- Day 18: exact `api-chain` plus hybrid-seeded `search-chain` APIs are covered.
- Day 19: one/two-hop GraphRAG expansion, deduplication, ranking, and `relation_reason` are covered.
- Day 20: Vue `GraphView`, Cytoscape graph, API integration, and node details are covered.
- Day 21: GraphRAG trace service, `/api/agent/trace`, required answer structure, and returned graph data are covered.
- Week 4 work is explicitly excluded.
