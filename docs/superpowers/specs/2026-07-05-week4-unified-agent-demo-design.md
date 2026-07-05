# Week 4 Unified Agent and Demo Design

**Date:** 2026-07-05  
**Status:** Approved design  
**Scope:** Week 4 of `plan.md`

## 1. Goal

Week 4 turns the existing code question-answering, graph tracing, and retrieval capabilities into one user-facing Agent workflow:

```text
User question
  -> SimpleAgentPlanner
  -> AgentExecutor
  -> existing or new task service
  -> unified response
  -> persist user and assistant messages
  -> frontend answer, references, and optional graph
```

The week must deliver three task types:

- `CODE_QA`: locate and explain code using the existing code-QA service.
- `TRACE_CHAIN`: explain frontend/backend or call chains using the existing trace service.
- `CHANGE_PLAN`: identify likely affected files and describe a grounded modification plan without changing code.

The result must remain aligned with the main plan: it is a small rule-driven Agent, not an autonomous coding system.

## 2. Explicit Scope Boundaries

Week 4 includes:

- a deterministic rule-based planner;
- a small typed tool registry;
- task routing through an Agent executor;
- a grounded change-planning service;
- a unified chat API;
- minimal conversation and message persistence;
- project, search, graph, and Agent chat frontend routes;
- automated offline tests and user-run manual acceptance tests;
- README and demo documentation.

Week 4 does not include:

- automatic source-code modification;
- LLM-based task classification;
- authentication or authorization;
- background task queues;
- multi-model routing;
- a general plugin framework;
- conversation history supplied to the LLM;
- automatic browser operation, OCR, or visual page analysis;
- repeated real-LLM acceptance calls.

Context-aware follow-up questions are deferred to a later milestone. That later design should use a bounded recent-message window, an explicit token budget, and citation requirements.

## 3. Architecture

### 3.1 SimpleAgentPlanner

`SimpleAgentPlanner` receives a question and returns one task type. It uses deterministic, testable rules:

- modification, addition, field, impact, risk, or “which files must change” language selects `CHANGE_PLAN`;
- data origin, chain, call relationship, frontend/backend flow, or tracing language selects `TRACE_CHAIN`;
- location, implementation, file, method, and general code questions select `CODE_QA`;
- an unrecognized question falls back to `CODE_QA`.

Change-plan indicators take priority over trace and code-location indicators because change requests often contain words such as “API”, “chain”, or “file”.

### 3.2 ToolRegistry

`ToolRegistry` is a typed mapping of stable tool names to application services. The initial registry exposes:

- `hybrid_search`;
- `graph_search`;
- `read_entity`;
- `get_related_entities`.

It is an internal dependency registry, not a dynamic plugin system. Registration failures and unknown tool names must produce explicit application errors.

### 3.3 AgentExecutor

`AgentExecutor` accepts the planner result and delegates to one task adapter:

- `CODE_QA` -> existing `CodeQaService`;
- `TRACE_CHAIN` -> existing `TraceService`;
- `CHANGE_PLAN` -> new `ChangePlanService`.

Each adapter converts its task-specific result into one unified Agent result containing:

- `task_type`;
- `answer`;
- `references`;
- `graph_nodes`;
- `graph_edges`;
- `uncertainties`.

The executor must not duplicate retrieval or LLM logic already owned by task services.

### 3.4 ChangePlanService

`ChangePlanService` combines hybrid retrieval, related graph entities, and entity content. Its prompt instructs the LLM to return a structured plan with:

- a concise summary;
- affected files and entities;
- the reason each item is relevant;
- suggested changes;
- risks;
- uncertainties that require human confirmation.

Every affected file must be backed by retrieved evidence. The service must reject or remove invented file references that are absent from the supplied retrieval context. Empty or weak evidence must produce an uncertainty-focused response instead of confident speculation.

`CHANGE_PLAN` generates a plan only. It never edits files or emits a patch.

## 4. Unified Chat and Persistence

### 4.1 Data Model

Add two database tables:

```text
conversations
  id
  project_id
  title
  created_at
  updated_at

messages
  id
  conversation_id
  role
  content
  task_type
  metadata_json
  created_at
```

`role` is restricted to `user` or `assistant`. Assistant metadata may store references, graph data, and uncertainties needed to restore the UI. It must not store API keys, full prompts, model credentials, or hidden configuration.

### 4.2 Chat API

`POST /api/agent/chat` accepts:

```json
{
  "project_id": 1,
  "question": "Where is the alert API implemented?",
  "conversation_id": null,
  "limit": 5
}
```

`conversation_id` is optional. If omitted, the service creates a conversation. If supplied, the conversation must exist and belong to the same project.

The response contains:

```json
{
  "conversation_id": 1,
  "message_id": 2,
  "task_type": "CODE_QA",
  "answer": "...",
  "references": [],
  "graph_nodes": [],
  "graph_edges": [],
  "uncertainties": []
}
```

The user question and successful assistant response are saved atomically after task execution succeeds. If retrieval or LLM execution fails, neither message is committed. A newly created empty conversation must also be rolled back.

### 4.3 Conversation Read API

`GET /api/agent/conversations/{conversation_id}` returns the conversation and its messages in chronological order. This makes persistence observable and allows the frontend to restore a saved conversation after a reload.

Saved history is display-only in Week 4. The executor and LLM receive only the current question.

## 5. Error Handling

The API must return clear, stable errors for:

- missing projects;
- missing conversations;
- a conversation that belongs to another project;
- an unavailable or unbuilt vector index;
- missing entities;
- unsupported tool names;
- malformed structured LLM output;
- upstream LLM failure.

Database writes must be transactionally rolled back on task failure. Application logs may include task type, project ID, conversation ID, duration, and error category, but must not expose API keys or complete private prompts.

## 6. Frontend Design

Add Vue Router navigation for:

- `/projects`;
- `/search`;
- `/graph`;
- `/chat`.

### 6.1 ProjectView

The project page registers a source project, triggers a scan, and displays project statistics. It reuses existing backend APIs and does not introduce a second project-management abstraction.

### 6.2 SearchView

The search page accepts keywords or natural-language queries and displays hybrid-search results with entity type, qualified name, file path, line range, score, and source.

### 6.3 AgentChat

The chat page provides:

- a project selector or project ID input consistent with the existing UI;
- five clickable demo questions;
- a question input and send action;
- visible task-type labels;
- answer text;
- references with file and line information;
- a code-detail dialog or panel opened from a reference;
- the existing graph panel when graph nodes and edges are returned;
- uncertainties for change-plan answers;
- restoration of a selected conversation through the conversation read API.

The page maintains the returned `conversation_id` for later messages, but those earlier messages are not sent as LLM context.

The implementation should follow the frontend's existing component and CSS patterns. Adding a large UI framework solely for Week 4 is out of scope.

## 7. Testing Strategy

Development follows TDD in small groups: first add a failing test, then the smallest implementation that makes it pass, then refactor while green.

Backend coverage includes:

- planner classification and precedence;
- registry lookup and unknown-tool behavior;
- executor routing and response normalization;
- grounded change-plan parsing and invented-file rejection;
- conversation and message persistence;
- transaction rollback on task failure;
- project/conversation mismatch;
- chat and conversation-read API integration;
- regression tests for existing code-QA and trace endpoints.

Frontend coverage includes:

- router configuration;
- chat request and response rendering;
- reference interaction;
- graph visibility;
- uncertainty rendering;
- conversation restoration;
- project and search page API behavior.

Automated tests use fake LLM clients, deterministic embedding substitutes, and isolated database/vector-store fixtures. They must not make real MiMo calls or download models.

Only after linting, type checking, builds, and all offline tests pass may the user perform a minimal real-MiMo acceptance test. One representative call is preferred unless a concrete failure requires another. Browser automation, screenshot interpretation, OCR, and other high-token visual capabilities require separate explicit user permission.

## 8. Demo and Documentation

README documentation must cover:

- project purpose and architecture;
- backend and frontend startup commands;
- environment variables with a blank API-key placeholder;
- database and vector-index preparation;
- key API examples;
- the four frontend routes;
- current limitations;
- the manual demo sequence.

The five stable demo scenarios are:

1. locate the alert-list API implementation;
2. trace the alert-trend data flow;
3. identify backend APIs used by a frontend device-status page;
4. locate an anomaly-detection entry function;
5. plan the files affected by adding a `risk_score` field.

Screenshots, if desired, are captured and reviewed manually by the user unless separate permission is given for browser or visual tooling.

## 9. Delivery Sequence

The implementation plan should divide Week 4 into reviewable tasks:

1. planner rules;
2. tool registry and executor;
3. grounded change-plan service;
4. conversation schema and persistence service;
5. unified chat and conversation-read APIs;
6. Agent chat frontend;
7. project, search, graph, and route integration;
8. documentation, regression testing, and manual acceptance preparation.

Each group should stop at a useful manual-test boundary before commit and push, following the project's established collaboration workflow.

## 10. Acceptance Criteria

Week 4 is complete when:

- all three task types are reachable through `POST /api/agent/chat`;
- planner behavior is deterministic and covered by tests;
- change plans cite only retrieved files and expose uncertainty;
- successful user and assistant messages persist and can be reloaded;
- saved history does not influence LLM context;
- all four frontend routes work;
- references and graph results are visible in Agent chat;
- backend and frontend offline test suites pass;
- the README enables a clean local demo;
- no automated test consumes real LLM tokens.
