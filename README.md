# ResearchCode-Agent

ResearchCode-Agent is a full-stack MVP for understanding mixed Java, Vue, and
Python repositories. It scans source code, extracts code entities and static
relationships, builds project-scoped search indexes, expands evidence through a
lightweight code graph, and answers code questions through one Agent API.

The project is designed around a simple rule: generated answers and change
plans must remain tied to indexed source evidence. Responses therefore include
file paths, line ranges, graph relationships, and explicit uncertainty where
the static index cannot prove a claim.

## What this project is and is not

ResearchCode-Agent helps a developer ask evidence-backed questions about a
local code repository, for example:

- "Where is the alert API implemented?"
- "Trace the frontend request to the backend service."
- "Which indexed files are likely affected by adding `risk_score`?"

It is a code-understanding and change-planning system, not an autonomous coding
agent. It does not edit the indexed repository, run arbitrary commands in that
repository, or let an LLM dynamically choose tools in a ReAct/function-calling
loop. Task selection is deterministic, and the LLM is used only after the
backend has retrieved bounded code and graph evidence.

The main design goal is useful uncertainty rather than confident guessing. A
missing static relation, an unavailable retrieval branch, an unresolved
frontend request, or an invalid generated citation is surfaced as an explicit
limitation or failure state instead of being converted into a code fact.

## Core concepts and trust boundaries

| Concept | Role | What it is trusted for | What it is not trusted for |
| --- | --- | --- | --- |
| Source scanner and parsers | Discover local source and configuration files, parse supported code into indexed entities, and record scan metadata and issues | File metadata, parsed entities, conservative static relations, scan issues | Runtime behavior, reflection, dynamic dispatch, arbitrary framework conventions |
| SQLite | Project-scoped static source-of-truth store | Code files, entities, relations, scan issues, conversations | Semantic vector similarity or runtime traces |
| Qdrant | Project-scoped vector store | Semantic ranking of indexed code chunks | Code graph facts or durable source metadata |
| Hybrid retrieval | Combines keyword and vector results | Candidate evidence for the current question | Proof that a candidate relationship exists |
| GraphRAG | Expands retrieved entities through stored SQLite relations | Bounded one- or two-hop static relationship evidence | A complete runtime call graph |
| LLM | Explains supplied evidence and generates a structured change plan | Natural-language synthesis within the supplied context | Inventing paths, line ranges, APIs, or relationships |
| Evidence validator | Checks generated citations and mentioned locations against current references | Returning only supported citation IDs, paths, and entity line ranges | Physical file line-count verification or semantic relationship verification |
| Conversation memory | Supplies a bounded recent window from the same conversation | Resolving follow-up wording and retaining local constraints | Cross-project facts, cross-conversation profiles, or code evidence |

The current request's indexed evidence is always the authority for code facts.
Conversation memory and prior LLM output can guide interpretation, but they do
not become proof on their own.

## How one Agent chat request works

```text
user question + project_id + optional conversation_id
        |
        +--> verify conversation belongs to the project
        |
        +--> load bounded same-conversation memory, if supplied
        |
        +--> deterministic task routing
        |      CODE_QA | TRACE_CHAIN | CHANGE_PLAN
        |
        +--> project-scoped keyword/vector retrieval
        |      one branch may degrade with an uncertainty
        |
        +--> optional one/two-hop SQLite graph expansion
        |
        +--> bounded cited context and authoritative stored graph edges
        |
        +--> LLM answer or structured change-plan generation
        |
        +--> validate citations, mentioned paths, and cited entity line ranges
        |      valid: return answer
        |      invalid: one evidence-directed repair request
        |      invalid again: guarded failure + references + uncertainties
        |
        +--> persist the successful user/assistant exchange atomically
```

The unified chat response contains an `answer`, numbered `references` with
`file_path`, `start_line`, and `end_line`, optional `graph_nodes` and
`graph_edges`, and an `uncertainties` list. Change planning internally creates
structured `affected_files` and `risks`, then renders grounded recommendations
into `answer`; `/api/agent/chat` does not currently expose separate
`affected_files` or `risks` response fields.

## Key capabilities

- Register a local source repository and scan supported text files.
- Parse Java, Vue, and Python with Tree-sitter and Python's built-in AST.
- Extract classes, methods, functions, backend APIs, and statically verified
  frontend API calls from Vue, JavaScript, and TypeScript.
- Persist code entities and directed relationships in SQLite.
- Build one Qdrant vector collection per registered project.
- Run keyword search or weighted keyword/vector hybrid search.
- Expand retrieved entities through a one- or two-hop code graph.
- Trace frontend request calls through backend APIs, controllers, and services.
- Diagnose recognized, backend-matched, unmatched, and unresolved frontend
  request candidates with source locations.
- Route questions to code QA, call-chain tracing, or grounded change planning.
- Validate generated citations, file paths, and cited line ranges before an
  answer is returned; allow at most one evidence-repair generation.
- Return citations, graph evidence, and explicit uncertainties; render grounded
  affected-file and risk recommendations in change-plan answer text.
- Save and reload project-isolated conversations, and use a bounded recent
  message window for same-conversation follow-up questions.
- Explore projects, search results, graph relationships, and conversations
  through a four-route Vue application.

## End-to-end architecture

```text
local source repository
        |
        v
safe file discovery and UTF-8 reading
        |
        +--> Java / Python declaration parsers
        |
        +--> Vue / JavaScript / TypeScript request extractor
        |
        +--> SQLite code files, entities, scan issues, and relations
        |
        +--> entity-based code chunks
                  |
                  v
          embedding provider
                  |
                  v
       project-scoped Qdrant collection
                  |
                  v
     keyword + vector hybrid retrieval
                  |
                  v
       one/two-hop graph expansion
                  |
                  v
       deterministic Agent planner
          /           |            \
      CODE_QA    TRACE_CHAIN    CHANGE_PLAN
          \           |            /
                  LLM
                   |
                   v
cited answer + graph evidence + uncertainty + bounded conversation memory
```

SQLite is the source of truth for the static code graph:

```text
code_entities  = graph nodes
code_relations = directed graph edges
```

No separate graph database is required. Qdrant is used only for semantic
retrieval.

## Technology stack

| Area | Technologies |
| --- | --- |
| Backend API | Python 3.11, FastAPI, Pydantic v2 |
| Persistence | SQLAlchemy, SQLite |
| Parsing | Python `ast`, Tree-sitter, `tree-sitter-language-pack` |
| Retrieval | keyword search, sentence-transformers or an OpenAI-compatible embedding API |
| Vector storage | Qdrant local storage or remote Qdrant |
| LLM | OpenAI-compatible chat API |
| Frontend | Vue 3, TypeScript, Vue Router, Axios, Vite |
| Graph UI | Cytoscape |
| Verification | pytest, pytest-cov, Vitest, Vue Test Utils |

## Source scanning and parsing

The scanner recognizes these extensions:

| Extensions | Recorded language |
| --- | --- |
| `.java` | Java |
| `.py` | Python |
| `.vue` | Vue |
| `.js`, `.jsx` | JavaScript |
| `.ts`, `.tsx` | TypeScript |
| `.sql` | SQL |
| `.xml` | XML |
| `.yml`, `.yaml` | YAML |
| `.json` | JSON |

Java and Python have general declaration parsers for classes and functions.
Vue, standalone JavaScript/JSX, and standalone TypeScript/TSX use the frontend
request extractor: it can create `frontend_api_call` entities, but it does not
create general JavaScript or TypeScript class/function entities. Other
recognized files contribute to scan statistics but do not produce searchable
entities. The system does not currently index arbitrary Markdown or project
documentation.

The scanner:

- skips common generated, dependency, IDE, virtual-environment, and Git
  directories;
- does not follow directory or file symbolic links;
- rejects files larger than `RCA_MAX_SOURCE_BYTES`;
- detects likely binary files from NUL bytes;
- accepts UTF-8 and UTF-8 with BOM;
- records skipped files and parser failures as structured scan issues;
- computes a SHA-256 hash and line count for every accepted file;
- replaces a project's previous static index atomically on a successful scan;
- prevents two scans of the same project from running concurrently.

### Parsed entity types

| Entity type | Source | Meaning |
| --- | --- | --- |
| `java_class` | Java | Parsed class declaration |
| `java_method` | Java | Parsed method with source range and invocation metadata |
| `backend_api` | Java | Spring-style HTTP endpoint associated with a method |
| `frontend_api_call` | Vue, JavaScript, TypeScript | Statically verified HTTP request from a Vue script block or standalone JS/TS file |
| `python_class` | Python | Python class parsed with the built-in AST |
| `python_function` | Python | Module-level function or class method |

Each entity stores its project, file path, qualified name, entity type, source
line range, indexed source content, and parser-specific metadata.

`frontend_api_call` can originate from a Vue `<script>` block or an independent
`.js`, `.jsx`, `.ts`, or `.tsx` file when its request URL and HTTP method are
statically resolvable. This is a dedicated request-analysis path, not a general
JavaScript/TypeScript language model.

### Static relation model

| Relation | Meaning | Typical confidence |
| --- | --- | --- |
| `CONTAINS` | A class contains a method or function | `1.0` |
| `DEFINES_API` | A Java method defines a backend HTTP endpoint | `1.0` |
| `REQUESTS_API` | A frontend request matches a backend method and normalized path | `1.0`; `0.8` for an `ANY`-method fallback |
| `CALLS_METHOD` | A Java method invokes a resolved service method | `0.8` for receiver-type resolution; `0.6` for a unique-name fallback |

Ambiguous method-name fallbacks do not create an edge. This intentionally
favours missing evidence over a guessed relationship.

## Retrieval and GraphRAG

### Code chunks and vector isolation

Every parsed entity becomes one code chunk containing:

- entity type and name;
- qualified name;
- file path and line range;
- parser metadata;
- at most `RCA_CHUNK_MAX_CONTENT_CHARS` characters of source.

Each project uses a separate Qdrant collection:

```text
project_{project_id}_code_chunks
```

This keeps vector results isolated between registered repositories. The same
embedding model and vector dimension must be used for indexing and querying.
External document embeddings are sent sequentially in batches of at most 64
texts to satisfy the Zhipu `embedding-3` request limit; vectors are merged back
in entity order before the Qdrant collection is rebuilt.

### Search modes

Keyword search queries the SQLite entity index and does not need Qdrant or an
embedding model.

Hybrid search requires a built vector index. It retrieves twice the requested
limit from both sources, normalizes positive scores independently, deduplicates
entities, and computes:

```text
hybrid_score = 0.75 * normalized_vector_score
             + 0.25 * normalized_keyword_score
```

These production weights were selected by a frozen Pilot grid calibration;
the [fusion-weight selection report](evaluation/reports/hybrid-fusion-weight-selection-report.md)
records the comparison, selection rule, and claim boundary.

When an operational failure makes either the vector or keyword branch
unavailable, hybrid retrieval can return results from the remaining branch and
attaches an uncertainty. A missing vector collection remains an explicit
configuration error; if both branches are unavailable, the request fails
instead of being reported as "not found".

GraphRAG uses the hybrid results as seed entities and expands their incoming
and outgoing SQLite relationships to a maximum depth of two. Traversal remains
within one project and deduplicates cycles.

## Agent behavior

### Deterministic planning

`SimpleAgentPlanner` classifies each normalized question by keywords:

| Task | Purpose |
| --- | --- |
| `CODE_QA` | Locate or explain indexed implementation details |
| `TRACE_CHAIN` | Explain data flow or frontend-to-backend call chains |
| `CHANGE_PLAN` | Identify evidence-backed files and risks for a requested change |

Change-planning keywords take precedence over trace keywords, which take
precedence over code-QA keywords. Questions that match no keyword default to
`CODE_QA`.

This is deterministic task routing, not autonomous LLM planning. The current
Agent does not ask an LLM to decompose a question into multiple tasks or select
tools. A `ToolRegistry` exposes named internal callables such as hybrid search
and graph traversal, but it is not currently an LLM function-calling loop.

### Task execution

- `CODE_QA` performs hybrid retrieval, builds a bounded cited context, and asks
  the configured LLM to answer only from that evidence. Its generated
  citations, file paths, and line ranges are checked against the current cited
  context before being returned.
- `TRACE_CHAIN` combines hybrid retrieval, graph expansion, a bounded graph
  context, and an LLM explanation. Its response also returns deterministic
  nodes, edges, and missing-chain uncertainties.
- `CHANGE_PLAN` retrieves and expands evidence, asks the LLM for structured
  JSON, validates it with Pydantic, and removes affected files that cannot be
  matched to an indexed reference. It produces a plan, not a code patch.

If answer-evidence validation fails, the Agent performs one repair request
with the previous answer, validation failures, and current evidence context.
If the repaired answer also fails, it returns a guarded overall failure message
with the validated references and uncertainty details instead of partially
rewriting natural-language claims.

All three real task types can consume provider tokens. Automated tests inject
deterministic fake LLM and embedding implementations.

### Conversations

`POST /api/agent/chat` stores a user message and its successful assistant
response in one transaction. A failed task does not save a partial exchange.
Conversation IDs are checked against their project to prevent cross-project
access.

For an existing conversation, the Agent reads at most the latest six persisted
messages, truncates each message to 600 characters and the entire memory block
to 4,000 characters, then labels that block as non-code evidence for retrieval
and generation. The current question still controls task routing and storage;
code facts must still be supported by current indexed evidence. New
conversations, different projects, and different conversations do not share
memory.

## Repository structure

```text
ResearchCode_Agent/
|-- backend/
|   |-- app/
|   |   |-- agent/       # task types, deterministic planner, executor, tools
|   |   |-- api/         # FastAPI route definitions
|   |   |-- core/        # settings, database, dependency factories
|   |   |-- graph/       # project-scoped graph queries and traversal types
|   |   |-- llm/         # OpenAI-compatible chat client
|   |   |-- models/      # SQLAlchemy persistence models
|   |   |-- parsers/     # Java/Python declaration parsers, frontend request extraction, and relation building
|   |   |-- rag/         # cited text/graph context and GraphRAG retrieval
|   |   |-- retrieval/   # chunks, embeddings, search, Qdrant adapter
|   |   |-- schemas/     # Pydantic request and response contracts
|   |   `-- services/    # application workflows
|   |-- scripts/         # offline indexing and inspection utilities
|   `-- tests/           # unit, integration, and acceptance tests
|-- frontend/
|   `-- src/
|       |-- api/         # typed Axios clients
|       |-- components/  # navigation, graph, and reference UI
|       |-- types/       # frontend API contracts
|       `-- views/       # project, search, graph, and Agent pages
`-- docs/superpowers/    # implementation designs and plans
```

## Prerequisites

- Windows PowerShell or Command Prompt
- Python 3.11
- Node.js 22 and npm
- an OpenAI-compatible chat endpoint for real Agent requests
- a Zhipu AI API key for the default `embedding-3` model
- local or remote Qdrant

Automated tests do not require credentials, paid APIs, Docker, or network
access.

## Configuration

From `backend`, copy `.env.example` to `.env`. Never commit `.env`.

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\backend
Copy-Item .env.example .env
```

Settings use the `RCA_` prefix:

| Variable | Default/example | Purpose |
| --- | --- | --- |
| `RCA_DATABASE_URL` | `sqlite+pysqlite:///./research_code_agent.db` | SQLAlchemy database URL |
| `RCA_MAX_SOURCE_BYTES` | `2097152` | Maximum accepted source-file size |
| `RCA_EMBEDDING_PROVIDER` | `api` | Default external embedding mode |
| `RCA_EMBEDDING_MODEL` | `embedding-3` | Zhipu multilingual embedding model |
| `RCA_EMBEDDING_API_KEY` | empty | Required for API embeddings |
| `RCA_EMBEDDING_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | Zhipu API base URL |
| `RCA_EMBEDDING_DIMENSIONS` | `1024` | Vector dimension sent to the provider |
| `RCA_QDRANT_URL` | empty | Remote URL; empty selects local storage |
| `RCA_QDRANT_API_KEY` | empty | Remote Qdrant credential |
| `RCA_QDRANT_PATH` | `./qdrant_storage` | Local Qdrant directory |
| `RCA_SEARCH_DEFAULT_LIMIT` | `10` | Configured default search limit |
| `RCA_SEARCH_MAX_LIMIT` | `50` | Configured maximum search limit |
| `RCA_CHUNK_MAX_CONTENT_CHARS` | `4000` | Maximum source characters per chunk |
| `RCA_LLM_API_KEY` | empty | Required for real Agent calls |
| `RCA_LLM_BASE_URL` | provider URL | OpenAI-compatible chat base URL |
| `RCA_LLM_MODEL` | provider model | Chat model name |
| `RCA_RAG_MAX_CONTEXT_CHARS` | `12000` | Maximum generated evidence context |

Chinese queries are rewritten once by the configured chat LLM into concise
English code-search keywords. The rewrite is used only for keyword/vector
retrieval; routing, final prompts, and saved conversations retain the original
question. English queries bypass rewriting. Rewrite failures fall back to the
original query, and answers are instructed to use the original question's
language. This adds one chat-model call for Chinese hybrid/Agent queries.

There is no local embedding fallback. If Zhipu is unavailable, keyword-only
search remains available. Changing model or dimension requires rebuilding all
vector indexes.

Keep credentials only in `backend/.env` or process environment variables. Do
not expose keys in commands, logs, screenshots, commits, or issue reports.

## Installation and startup

### Backend

Create a conventional virtual environment:

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

This repository may also be used with an existing Conda-prefix-style
environment whose interpreter is `backend\.venv\python.exe`:

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\backend
.\.venv\python.exe -m uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. FastAPI documentation is available at
`http://127.0.0.1:8000/docs`, and `GET /health` returns `{"status":"ok"}`.
Database tables are created during application startup.

### Frontend

In another terminal:

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to
`http://127.0.0.1:8000`.

## Prepare a project

The indexed target must be an existing local directory accessible to the
backend process.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/projects `
  -H "Content-Type: application/json" `
  -d '{"name":"Demo","root_path":"F:/absolute/path/to/project"}'

curl.exe -X POST http://127.0.0.1:8000/api/projects/1/scan
curl.exe -X POST http://127.0.0.1:8000/api/projects/1/build-vector-index
curl.exe http://127.0.0.1:8000/api/projects/1/stats
```

The required order is:

1. register the project;
2. scan files and build the SQLite entity/relationship index;
3. build the Qdrant vector index;
4. use hybrid search, GraphRAG, or Agent endpoints.

Running a new static scan replaces the SQLite index. Rebuild the vector index
after source changes so semantic retrieval matches the latest entities.

In PowerShell, use `curl.exe`; `curl` may resolve to a PowerShell alias.

## Frontend routes

| Route | Purpose |
| --- | --- |
| `/projects` | Register, scan, index, and inspect project statistics |
| `/search` | Run hybrid search and inspect ranked code entities |
| `/graph` | Search and visualize code relationships |
| `/chat` | Ask Agent questions and reload saved conversations |

`/` redirects to `/projects`.

## API reference

### Projects and indexing

```http
POST /api/projects
GET  /api/projects
PUT  /api/projects/order
DELETE /api/projects/{project_id}
POST /api/projects/{project_id}/scan
GET  /api/projects/{project_id}/stats
GET  /api/projects/{project_id}/entities/{entity_id}
POST /api/projects/{project_id}/build-vector-index
GET  /api/projects/{project_id}/vector-index-status
GET  /api/projects/{project_id}/frontend-request-diagnostics?limit=10
```

`GET /api/projects` returns every registered project, ordered by persisted
manual order and project ID. The Projects page loads that complete result and
provides client-side filtering, sorting, and pagination; pagination limits only
the visible page, not the fetched project set. Manual drag order is persisted
in SQLite. Existing databases are upgraded automatically with the required
`sort_order` column. Deleting a project is irreversible: its database-owned
scan data and conversations are cascade-deleted after its Qdrant collection is
removed.

Projects-page shortcuts pass `project_id` to `/search`, `/graph`, and `/chat`;
those pages use a valid positive query value as their initial project ID.

Project creation body:

```json
{
  "name": "Demo",
  "root_path": "F:/absolute/path/to/project"
}
```

The entity endpoint returns indexed source for one entity, including its
qualified name, file path, and line range.

The frontend-request diagnostics endpoint reports counts and bounded examples
for recognized calls, calls matched to backend APIs, recognized but unmatched
calls, and unresolved request candidates. It reads only SQLite entities,
relations, and scan issues; it does not call an LLM.

### Search

```http
POST /api/search/keyword
POST /api/search/hybrid
```

Both accept:

```json
{
  "project_id": 1,
  "query": "where is alert lookup implemented",
  "limit": 5
}
```

Hybrid search returns HTTP `409` with `VECTOR_INDEX_NOT_FOUND` if the project
has no vector collection.

### Graph

Query a known HTTP API without embeddings:

```http
GET /api/graph/api-chain?project_id=1&method=GET&api_path=/api/alerts/123
```

Search for seed entities and expand their graph:

```http
POST /api/graph/search-chain
```

```json
{
  "project_id": 1,
  "query": "alert API",
  "limit": 5,
  "max_depth": 2
}
```

Graph responses contain structured `nodes`, `edges`, and numbered source
`references`.

### Agent

```http
POST /api/agent/code-qa
POST /api/agent/trace
POST /api/agent/chat
GET  /api/agent/conversations/{conversation_id}?project_id={project_id}
```

Direct code QA:

```json
{
  "project_id": 1,
  "question": "Where is the alert API implemented?",
  "limit": 5
}
```

Direct trace requests also accept `max_depth`, from `1` to `2`.

Unified chat chooses the task type:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/agent/chat `
  -H "Content-Type: application/json" `
  -d '{"project_id":1,"question":"Trace the alert request chain.","limit":5}'
```

Continue saving messages to the same conversation by including the returned
ID:

```json
{
  "project_id": 1,
  "question": "Which files need changes to add a risk_score field?",
  "conversation_id": 1,
  "limit": 5
}
```

The conversation is continuous for storage, display, and bounded
same-conversation working memory. Only the latest persisted messages from the
same project and conversation are supplied as non-code context; they do not
replace current indexed evidence.

## Offline scripts

Run scripts from `backend` with the environment's Python interpreter:

```powershell
.\.venv\python.exe -m scripts.scan_project F:\absolute\path\to\project
.\.venv\python.exe -m scripts.index_project F:\absolute\path\to\project --name Demo
.\.venv\python.exe -m scripts.search_vectors 1 "alert API"
.\.venv\python.exe -m scripts.trace_api_chain 1 GET /api/alerts/123
.\.venv\python.exe -m scripts.show_conversation 1
```

`scan_project` only reports file statistics and issues. `index_project`
registers the path when necessary and rebuilds its SQLite static index; it does
not build the Qdrant vector collection. Additional scripts can inspect parsed
entities, chunks, RAG context, API relations, and request classification.
Read-only SQLite inspection scripts do not invoke an LLM. Vector and RAG
scripts may initialize the configured embedding provider.

## Testing and verification

Backend tests use temporary SQLite databases, deterministic fake embeddings,
in-memory Qdrant, and fake LLM responses where appropriate.

Using the repository's existing Conda-prefix-style environment:

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\backend
.\.venv\python.exe -m pytest
.\.venv\python.exe -m pytest --cov=app --cov-report=term-missing
.\.venv\python.exe -m compileall -q app scripts tests
```

Focused offline acceptance flows:

```powershell
.\.venv\python.exe -m pytest tests\integration\test_week2_acceptance.py -v
.\.venv\python.exe -m pytest tests\integration\test_week3_acceptance.py -v
.\.venv\python.exe -m pytest tests\integration\test_week4_acceptance.py -v
```

Frontend:

```powershell
Set-Location F:\LIUQINGYUN\ResearchCode_Agent\frontend
npm.cmd test -- --run
npm.cmd run build
```

The backend coverage configuration requires at least 80% branch coverage.

## Reliability and safety properties

- Database and vector queries are scoped by `project_id`.
- Duplicate project root paths are rejected.
- Concurrent scans of the same project return a conflict instead of racing.
- Unsupported, oversized, binary, linked, unreadable, or invalid UTF-8 files
  become scan issues rather than silent index corruption.
- Ambiguous service-method calls are omitted instead of guessed.
- RAG contexts have a configurable character limit.
- A vector or keyword retrieval branch can degrade to the other available
  branch with an explicit uncertainty; total retrieval failure remains an
  explicit error.
- Code-QA prompts require source-grounded answers and structured references.
- Generated citation IDs, mentioned file paths, and cited line ranges are
  validated against the current RAG references; one bounded repair attempt is
  permitted before a guarded failure response is returned.
- Trace and change-plan prompts receive authoritative stored graph edges and
  deterministic notices for missing expected relation types.
- Change-plan output is schema-validated and ungrounded files are removed.
- Conversation writes are transactional and roll back on task failure;
  same-conversation memory is project-isolated and size-bounded.
- Real provider credentials are not needed by the automated tests.

## Known limitations

- Static analysis cannot prove runtime behavior.
- Reflection, dynamic dispatch, custom dependency-injection factories,
  inherited methods, generated constructors, framework proxies, and arbitrary
  computed URLs may not produce relationships.
- Java method-call resolution focuses on service methods and a limited set of
  Spring dependency-injection patterns.
- Vue, JavaScript, and TypeScript request extraction targets statically
  recognizable Axios, Fetch, direct `request`, and common wrapper expressions.
  Dynamic URLs, methods, constants, and unknown wrappers are reported as scan
  issues rather than guessed as graph facts.
- Java and Python produce general declaration entities. Vue, JavaScript/JSX,
  and TypeScript/TSX can additionally produce only statically verified
  `frontend_api_call` entities; recognized configuration and data files are not
  searchable chunks.
- Graph traversal is limited to two hops and four relation types.
- A code entity is truncated to the configured character limit before
  embedding and RAG use.
- Change planning generates recommendations, not patches.
- Conversation memory is a recent-message window, not a cross-conversation
  profile or a durable summary of long discussions.
- Evidence path and line-range validation is bounded by the current retrieved
  entity references; it does not independently verify a file's physical total
  line count or remap an invalid path to a nearest candidate.
- Graph relationship grounding relies on authoritative graph context and prompt
  constraints; it does not yet semantically validate every natural-language
  relationship claim after generation.
- Indexing is synchronous and provides no background progress, cancellation,
  or incremental update API.
- The frontend loads every registered project but does not provide a browseable
  list of every saved conversation; restoring a conversation currently requires
  its project ID and conversation ID.
- External embedding depends on network availability, account balance, and
  provider rate limits.
- The Cytoscape production bundle may emit a non-blocking large-chunk warning.
- No large-repository throughput or maximum-line-count claim has been
  benchmark-validated.

## Roadmap

The following ideas are not implemented in the current MVP:

- import/module dependency entities and relationships;
- Markdown and project-documentation indexing;
- bounded conversation summaries for long context-aware follow-up questions;
- LLM-selected tool calling and multi-step task decomposition;
- background indexing with progress, cancellation, and incremental updates;
- broader language support and stronger symbol resolution;
- runtime trace ingestion to complement static evidence;
- repository-scale performance benchmarks.

## Project evolution

| Milestone | Delivered capability |
| --- | --- |
| Week 1 | Registration, safe scanning, Java/Vue/Python entities, APIs, and relations |
| Week 2 | Code chunks, embeddings, Qdrant, keyword/vector/hybrid search, cited code QA |
| Week 3 | Graph traversal, GraphRAG, API-chain tracing, graph visualization |
| Week 4 | Unified Agent routing, grounded change plans, conversations, four-page demo |

Detailed backend notes and additional examples are available in
[`backend/README.md`](backend/README.md).
