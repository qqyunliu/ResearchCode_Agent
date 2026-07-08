# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ResearchCode-Agent is a full-stack code-understanding agent for mixed Java/Vue/Python repositories. It scans source code, extracts entities and static relationships into SQLite, builds per-project vector indexes in Qdrant, and answers code questions through a deterministic planner routing to three task types: `CODE_QA`, `TRACE_CHAIN`, `CHANGE_PLAN`.

The guiding principle: every answer and change plan must cite indexed source evidence (file paths, line ranges, graph relationships). Where evidence is missing, the system reports uncertainty rather than guessing.

## Tech stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy, SQLite |
| Parsing | Python `ast`, Tree-sitter (`tree-sitter-language-pack`) |
| Retrieval | sentence-transformers / Zhipu embedding-3, Qdrant |
| LLM | OpenAI-compatible chat API |
| Frontend | Vue 3, TypeScript, Vue Router, Axios, Vite |
| Graph UI | Cytoscape |
| Testing | pytest (backend), Vitest + Vue Test Utils (frontend) |

## Common commands

All backend commands run from the `backend/` directory using `.\.venv\python.exe` (the repository's Conda-prefix environment).

```powershell
# Backend: run dev server
.\.venv\python.exe -m uvicorn app.main:app --reload

# Backend: run all tests
.\.venv\python.exe -m pytest

# Backend: run tests with coverage (80% branch minimum enforced)
.\.venv\python.exe -m pytest --cov=app --cov-report=term-missing

# Backend: run a single test file
.\.venv\python.exe -m pytest tests/unit/test_scanner.py -v

# Backend: run a single test function
.\.venv\python.exe -m pytest tests/unit/test_scanner.py::test_function_name -v

# Backend: run weekly acceptance tests
.\.venv\python.exe -m pytest tests/integration/test_week2_acceptance.py -v
.\.venv\python.exe -m pytest tests/integration/test_week3_acceptance.py -v
.\.venv\python.exe -m pytest tests/integration/test_week4_acceptance.py -v

# Backend: syntax check
.\.venv\python.exe -m compileall -q app scripts tests

# Frontend: run from frontend/
npm.cmd run dev
npm.cmd test -- --run
npm.cmd run build
```

## Architecture

### Backend (`backend/app/`)

| Directory | Purpose |
|---|---|
| `agent/` | Deterministic planner (`SimpleAgentPlanner`), executor, tool registry, task types |
| `api/` | FastAPI route definitions (project, search, graph, agent) |
| `core/` | Settings (`RCA_` prefixed env vars via pydantic-settings), database session, dependency factories |
| `graph/` | Project-scoped BFS graph queries over SQLite `code_entities`/`code_relations` |
| `llm/` | OpenAI-compatible chat client |
| `models/` | SQLAlchemy ORM models |
| `parsers/` | Java (Spring annotations), Vue (axios/request calls), Python (`ast`) parsers + relation builder |
| `rag/` | Cited text/graph context builders, GraphRAG retriever |
| `retrieval/` | Code chunk builder, embedding service, keyword search, hybrid search, Qdrant adapter |
| `schemas/` | Pydantic request/response contracts |
| `services/` | Application workflows (scan, index, QA, trace, change plan, conversation) |
| `scripts/` | Offline CLI utilities for indexing and inspection |

### Frontend (`frontend/src/`)

| Directory | Purpose |
|---|---|
| `api/` | Typed Axios clients for each backend endpoint group |
| `components/` | Navigation, graph visualization (Cytoscape), code reference UI |
| `types/` | TypeScript API contracts |
| `views/` | Four route pages: Project, Search, Graph, Agent Chat |
| `utils/` | Shared utilities |

### Data flow

```text
register project -> scan files -> parse entities -> build SQLite index
                                                    -> build Qdrant vector index
                                                    -> hybrid search / graph traversal / Agent chat
```

SQLite is the source of truth for the static code graph (`code_entities` = nodes, `code_relations` = edges). Qdrant is used only for semantic vector retrieval. Each project gets its own Qdrant collection: `project_{id}_code_chunks`.

### Agent task routing

`SimpleAgentPlanner` uses keyword matching (not LLM) to classify questions:
- CHANGE_PLAN keywords take precedence over TRACE_CHAIN, which takes precedence over CODE_QA
- Default fallback is `CODE_QA`

### Key design decisions

- **No graph database**: SQLite tables simulate a directed graph with BFS traversal (max 2 hops).
- **Deterministic planning**: Task routing is rule-based, not LLM-driven.
- **Evidence-grounded answers**: Prompts require source citations; ungrounded claims are filtered out.
- **Per-project isolation**: All queries (SQLite, Qdrant) are scoped by `project_id`.
- **No conversation memory**: Saved messages are for display/reload only, not injected into later prompts.
- **Scan replaces index**: A new scan atomically replaces the previous SQLite static index; vector index must be rebuilt separately.

## Configuration

Settings use `RCA_` prefix, loaded from `backend/.env` (never committed). Key variables: `RCA_DATABASE_URL`, `RCA_EMBEDDING_API_KEY`, `RCA_LLM_API_KEY`, `RCA_QDRANT_PATH`, `RCA_RAG_MAX_CONTEXT_CHARS`.

Chinese queries are rewritten once by the LLM into English code-search keywords for retrieval; the original question is preserved in planning, prompts, and conversation storage.

## Testing approach

Backend tests use temporary SQLite databases, deterministic fake embeddings, in-memory Qdrant, and fake LLM responses. No credentials, Docker, or network access needed for tests. Coverage threshold: 80% branch.

Frontend tests use Vitest with jsdom environment.

## Project preparation workflow

Required order to use the system:
1. `POST /api/projects` — register project with `name` and `root_path`
2. `POST /api/projects/{id}/scan` — scan files, build SQLite entity/relationship index
3. `POST /api/projects/{id}/build-vector-index` — build Qdrant vector collection
4. Use search, graph, or Agent endpoints
