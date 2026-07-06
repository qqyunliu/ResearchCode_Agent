# ResearchCode-Agent

ResearchCode-Agent is a four-week MVP for indexing a mixed Java, Vue, and
Python repository and answering grounded questions about its code. It combines
static parsing, SQLite relationships, hybrid retrieval, a lightweight graph,
and an OpenAI-compatible LLM behind one Agent API and a four-route Vue demo.

## What the MVP does

```text
source project
  -> scan Java / Vue / Python
  -> store files, entities, APIs, and relations in SQLite
  -> build vector chunks in Qdrant
  -> keyword + vector hybrid retrieval
  -> one/two-hop graph expansion
  -> deterministic Agent planning
  -> code QA, call-chain trace, or grounded change plan
  -> cited answer, graph evidence, uncertainties, and saved conversation
```

The Agent planner is deterministic. It routes questions to:

- `CODE_QA` for implementation and location questions;
- `TRACE_CHAIN` for frontend-to-backend and call-flow questions;
- `CHANGE_PLAN` for requests asking what code must change.

Saved conversations are for display and reload only. Earlier messages are not
inserted into later LLM prompts.

## Four-week architecture

| Week | Delivered capability |
| --- | --- |
| 1 | Project registration, scanning, Java/Vue/Python entities, APIs, and relations |
| 2 | Code chunks, embeddings, Qdrant, keyword/vector/hybrid search, grounded code QA |
| 3 | Graph traversal, GraphRAG retrieval, frontend/API/controller/service tracing |
| 4 | Unified Agent, grounded change plans, conversations, and four-page Vue demo |

## Prerequisites

- Windows CMD or PowerShell;
- Python 3.11 environment available as `backend\.venv\python.exe`;
- Node.js 22 and npm;
- an OpenAI-compatible chat API for real Agent calls;
- either a local sentence-transformer or compatible embedding API;
- Qdrant local storage or remote Qdrant.

Automated tests use deterministic substitutes and do not require paid APIs.

## Configuration

From `backend`, copy `.env.example` to `.env` and fill credentials locally.
Never commit `.env`.

```dotenv
RCA_DATABASE_URL=sqlite+pysqlite:///./research_code_agent.db

RCA_EMBEDDING_PROVIDER=local
RCA_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RCA_EMBEDDING_API_KEY=
RCA_EMBEDDING_BASE_URL=

RCA_QDRANT_URL=
RCA_QDRANT_API_KEY=
RCA_QDRANT_PATH=./qdrant_storage

RCA_LLM_API_KEY=
RCA_LLM_BASE_URL=https://api.xiaomimimo.com/v1
RCA_LLM_MODEL=mimo-v2.5
```

Real `/api/agent/*` calls consume provider tokens. Do not expose API keys in
commands, screenshots, logs, or commits.

## Start the application

Backend, from CMD:

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week4-unified-agent-demo\backend
.venv\python.exe -m uvicorn app.main:app --reload
```

Frontend, in another CMD:

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week4-unified-agent-demo\frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`.

## Prepare a project

The Projects page supports the full workflow:

1. enter a project name and absolute source path;
2. register the project;
3. scan it;
4. build its vector index;
5. note the returned project ID and indexed chunk count.

Equivalent CMD calls:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/projects -H "Content-Type: application/json" -d "{\"name\":\"Demo\",\"root_path\":\"F:\\absolute\\path\\to\\project\"}"
curl.exe -X POST http://127.0.0.1:8000/api/projects/1/scan
curl.exe -X POST http://127.0.0.1:8000/api/projects/1/build-vector-index
curl.exe http://127.0.0.1:8000/api/projects/1/stats
```

In PowerShell, use `curl.exe`; plain `curl` may resolve to a PowerShell alias
with different argument behavior.

## Frontend routes

| Route | Purpose |
| --- | --- |
| `/projects` | Register, scan, index, and inspect project statistics |
| `/search` | Run hybrid code search and inspect ranked entities |
| `/graph` | Search and visualize code relationships |
| `/chat` | Ask unified Agent questions and restore saved conversations |

## Core APIs

```http
POST /api/projects
POST /api/projects/{project_id}/scan
GET  /api/projects/{project_id}/stats
POST /api/projects/{project_id}/build-vector-index
GET  /api/projects/{project_id}/entities/{entity_id}

POST /api/search/keyword
POST /api/search/hybrid

GET  /api/graph/api-chain
POST /api/graph/search-chain

POST /api/agent/code-qa
POST /api/agent/trace
POST /api/agent/chat
GET  /api/agent/conversations/{conversation_id}?project_id={project_id}
```

Unified chat example:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/agent/chat -H "Content-Type: application/json" -d "{\"project_id\":1,\"question\":\"Where is the alert API implemented?\",\"limit\":5}"
```

Continue a conversation by sending the returned ID:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/agent/chat -H "Content-Type: application/json" -d "{\"project_id\":1,\"question\":\"Trace the alert request chain.\",\"conversation_id\":1,\"limit\":5}"
```

## Stable demo questions

1. `Where is the alert-list API implemented?`
2. `Where does the alert-trend data flow come from?`
3. `Which backend APIs are used by the device-status page?`
4. `Where is the anomaly-detection entry function?`
5. `Which files need changes to add a risk_score field?`

Answers are limited by indexed evidence. A correct result may explicitly say
that a requested feature is absent from the repository.

## Verification

Backend:

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week4-unified-agent-demo\backend
.venv\python.exe -m pytest
.venv\python.exe -m pytest --cov=app --cov-report=term-missing
.venv\python.exe -m compileall -q app scripts tests
.venv\python.exe -m pytest tests\integration\test_week4_acceptance.py -v
```

Frontend:

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week4-unified-agent-demo\frontend
npm.cmd test -- --run
npm.cmd run build
```

Inspect a saved conversation without an LLM call:

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week4-unified-agent-demo\backend
.venv\python.exe -m scripts.show_conversation 1
```

## Current limitations

- Static parsing does not prove runtime behavior, reflection, dynamic dispatch,
  framework proxies, or arbitrary computed URLs.
- Change planning produces grounded recommendations, not patches.
- Conversation history is not reasoning memory; context-aware follow-up is a
  future milestone requiring bounded summaries and explicit grounding.
- Index builds are synchronous and have no background progress or cancellation.
- The frontend does not list every saved project or conversation.
- Local embedding startup may download a model if it is not already cached.
- The production bundle includes Cytoscape and currently emits a non-blocking
  large-chunk warning.

Detailed backend behavior and additional API examples are documented in
[`backend/README.md`](backend/README.md).
