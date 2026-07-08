# Project Collaboration Instructions

The user is developing this project both to build the software and to learn the
relevant engineering knowledge.

For every implementation step:

- Explain what is being changed and why it is needed.
- Explain the relevant technical concepts in accessible language.
- Point out meaningful alternatives and trade-offs when they affect the design.
- Mention common mistakes or risks that are useful for learning.
- Work in small steps and obtain the user's opinion before moving to the next
  implementation step.
- After verification succeeds on an isolated feature branch, treat committing
  and pushing that branch as one step. Request separate confirmation for work
  that affects `main`, merges branches, deletes branches, or performs another
  high-impact repository operation.

## High-token capabilities

- Do not use potentially high-token capabilities without the user's explicit
  permission for that specific use.
- This includes OCR or image-text recognition, visual webpage analysis,
  browser-driven frontend inspection or interaction, repeated real-LLM calls,
  and similar token-intensive tools.
- Prefer local automated tests, builds, structured API responses, and direct
  text/code inspection when they can verify the same behavior.
- Before requesting permission, explain why the high-token capability is
  necessary and give a lower-cost alternative when one exists.

# Project Quick Context

Use this section to quickly regain project context in a fresh AI-assistant
conversation.

## What this project is

ResearchCode-Agent is a full-stack code-understanding agent for mixed
Java/Vue/Python repositories. It registers local source projects, scans code
into a SQLite static index, builds a per-project Qdrant vector index, and then
supports:

- code semantic/keyword search;
- GraphRAG-style call-chain tracing;
- evidence-grounded Agent chat for code Q&A, tracing, and change planning.

The core promise is not "free-form coding automation" yet. The current backend
is better described as an evidence-grounded agentic workflow: deterministic
task routing plus RAG/GraphRAG service orchestration.

## Current high-level architecture

- Backend: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy, SQLite.
- Frontend: Vue 3, TypeScript, Vue Router, Axios, Vite.
- Vector retrieval: Qdrant, configured through `RCA_` environment variables.
- Embeddings: currently designed for OpenAI-compatible external embeddings,
  with Zhipu `embedding-3` used in local configuration.
- LLM: OpenAI-compatible chat API.
- Graph UI: Cytoscape via the frontend graph panel.

Important backend directories:

- `backend/app/api/`: FastAPI endpoints.
- `backend/app/services/`: project workflows such as scan, indexing, QA,
  trace, change plan, and conversation persistence.
- `backend/app/retrieval/`: embedding, Qdrant vector store, keyword search,
  hybrid search, query rewriting.
- `backend/app/graph/`: SQLite-backed graph traversal over code entities and
  code relations.
- `backend/app/rag/`: cited RAG context builders and GraphRAG retriever.
- `backend/app/agent/`: task types, deterministic planner, executor, tool
  registry.
- `backend/app/parsers/`: Java, Vue, Python parsers and relation extraction.

Important frontend directories:

- `frontend/src/views/`: Project, Search, Graph, and Agent Chat pages.
- `frontend/src/api/`: typed Axios clients.
- `frontend/src/types/`: frontend API contracts.
- `frontend/src/components/`: shared UI, graph panel, dialogs.
- `frontend/src/utils/`: route and local-history utilities.

## Core data flow

The required usage order is:

1. Register project: `POST /api/projects`.
2. Scan source files: `POST /api/projects/{project_id}/scan`.
3. Build vector index: `POST /api/projects/{project_id}/build-vector-index`.
4. Use search, graph, or Agent endpoints.

SQLite is the source of truth for scanned code entities and static
relationships. Qdrant stores semantic vectors only. Each project has its own
Qdrant collection named `project_{project_id}_code_chunks`.

## Agent chat endpoint

Frontend calls:

```text
POST /api/agent/chat
```

Request shape:

```json
{
  "project_id": 1,
  "question": "Where is the alert list API implemented?",
  "conversation_id": 12,
  "limit": 5
}
```

Response shape:

```json
{
  "conversation_id": 12,
  "message_id": 88,
  "task_type": "CODE_QA",
  "answer": "...",
  "references": [],
  "graph_nodes": [],
  "graph_edges": [],
  "uncertainties": []
}
```

`references` carry file path and line-range evidence. `graph_nodes` and
`graph_edges` carry graph evidence for trace/change-plan answers.

## Current Agent implementation reality

Be precise when describing this project to technical reviewers:

- `SimpleAgentPlanner` is keyword/rule based, not LLM based.
- `AgentExecutor` dispatches to one of three fixed task services:
  `CODE_QA`, `TRACE_CHAIN`, or `CHANGE_PLAN`.
- `ToolRegistry` exists and registers tools such as `hybrid_search` and
  `graph_search`, but current chat execution does not yet perform dynamic
  LLM-selected tool calls.
- Conversation history is persisted for display/reload, but previous messages
  are not currently injected into later RAG prompts as memory.

This means the current system is not yet a full ReAct/function-calling
autonomous Agent. It is a deterministic agentic workflow with evidence
grounding.

## Evidence model

Code Q&A uses:

- hybrid search = vector retrieval + keyword search;
- optional Chinese-to-English query rewriting for retrieval;
- cited RAG context blocks with `[n] file:start-end`;
- LLM prompt rules requiring same-language answers and citations.

Trace and change-plan tasks additionally use:

- `GraphRagRetriever`;
- SQLite graph traversal over relation types such as `REQUESTS_API`,
  `DEFINES_API`, and `CALLS_METHOD`;
- `GraphContextBuilder`, which includes authoritative stored graph edges in
  the LLM context.

When evidence is missing, services return explicit uncertainty instead of
guessing.

## Known important limitations

- The Agent planner is deterministic keyword matching.
- Dynamic tool selection is not implemented even though a tool registry exists.
- Unified `/api/agent/chat` responses do not expose structured
  `affected_files`, even though `ChangePlanService` internally produces them.
- Vector index rebuild is separate from source scan; after scanning changes,
  users must rebuild the vector index.
- Static analysis is best-effort and can miss dynamic calls, reflection,
  runtime routing, or framework conventions not covered by parsers.

## Local development commands

Backend commands usually run from `backend/`:

```powershell
.\.venv\python.exe -m uvicorn app.main:app --reload
.\.venv\python.exe -m pytest
.\.venv\python.exe -m compileall -q app scripts tests
```

Frontend commands usually run from `frontend/`:

```powershell
npm.cmd run dev
npm.cmd test
npm.cmd run build
```

PowerShell may block `npm.ps1`; prefer `npm.cmd`.

## Current collaboration preference

The user is using the project to learn engineering, not only to ship features.
For meaningful code changes, explain:

- what is being changed;
- why it matters;
- relevant concepts;
- alternatives and trade-offs;
- risks and common mistakes.

Do not commit or push unless the user explicitly asks.
