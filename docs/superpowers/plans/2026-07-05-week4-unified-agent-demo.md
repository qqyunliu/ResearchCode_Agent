# Week 4 Unified Agent and Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the existing code-QA and trace capabilities with grounded change planning, minimal saved conversations, a unified Agent API, and a complete four-route Vue demo.

**Architecture:** A deterministic `SimpleAgentPlanner` classifies each question as `CODE_QA`, `TRACE_CHAIN`, or `CHANGE_PLAN`; a typed `ToolRegistry` and `AgentExecutor` route work to focused services and normalize their outputs. SQLite stores conversations for display and reload only—saved messages do not enter the LLM prompt. Existing retrieval, graph, code-QA, and trace components remain the source of truth and are composed rather than duplicated.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Pydantic 2, SQLite, existing Qdrant/hybrid retrieval and OpenAI-compatible MiMo client, pytest, Vue 3, TypeScript, Vue Router, Axios, Cytoscape.js, Vitest.

---

## Scope and execution rules

- This plan implements Day 22 through Day 28 and closes the four-week MVP in `plan.md`.
- Work must occur in a dedicated Week 4 branch and worktree created at execution time.
- Follow TDD for each behavior: add a focused failing test, observe RED, implement the minimum, observe GREEN, then run regression tests.
- Automated tests must use fake LLMs and deterministic local test doubles. They must not download a model or make a real MiMo request.
- Do not use browser automation, OCR, webpage visual analysis, or screenshot interpretation without separate explicit user permission.
- Do not implement LLM-based planning, automatic code changes, authentication, background queues, a plugin framework, or full Memory.
- Conversation persistence is save-and-reload only. Previous messages must never be placed in the current LLM prompt.
- A successful chat request saves its user and assistant messages atomically. A failed task saves neither message nor a newly created empty conversation.
- After every task:
  1. run the focused automated checks;
  2. explain the new concepts and behavior;
  3. give the user a CMD-compatible manual test;
  4. stop and wait for confirmation;
  5. only after confirmation, commit and push that task to the isolated branch.
- Merging or pushing `main` always requires a separate explicit instruction.

## File map

| Path | Responsibility |
| --- | --- |
| `backend/app/agent/types.py` | Task type and unified internal Agent result |
| `backend/app/agent/planner.py` | Deterministic task classification |
| `backend/app/agent/tool_registry.py` | Typed lookup of registered application tools |
| `backend/app/agent/executor.py` | Task routing and response normalization |
| `backend/app/services/change_plan_service.py` | Grounded retrieval and change-plan generation |
| `backend/app/models/conversation.py` | Conversation database model |
| `backend/app/models/message.py` | Persisted user/assistant message model |
| `backend/app/services/conversation_service.py` | Conversation validation, atomic persistence, and reload |
| `backend/app/services/agent_chat_service.py` | Planner → executor → persistence orchestration |
| `backend/app/schemas/agent.py` | Change-plan, chat, and conversation HTTP contracts |
| `backend/app/api/agent_api.py` | Unified chat and conversation-read endpoints |
| `frontend/src/router.ts` | Four-route Vue Router configuration |
| `frontend/src/api/projects.ts` | Project registration, scan, and stats requests |
| `frontend/src/api/search.ts` | Hybrid-search requests |
| `frontend/src/api/agent.ts` | Chat and conversation requests |
| `frontend/src/views/ProjectView.vue` | Project setup and statistics |
| `frontend/src/views/SearchView.vue` | Hybrid-search UI |
| `frontend/src/views/AgentChat.vue` | Unified Agent conversation UI |
| `frontend/src/components/ReferenceDialog.vue` | Reference and code-content detail |
| `frontend/src/components/AppNav.vue` | Route navigation |

---

### Task 1: Implement `SimpleAgentPlanner` (Day 22)

**Files:**
- Create: `backend/app/agent/__init__.py`
- Create: `backend/app/agent/types.py`
- Create: `backend/app/agent/planner.py`
- Create: `backend/scripts/classify_agent_question.py`
- Create: `backend/tests/unit/test_agent_planner.py`

- [x] **Step 1: Write failing classification tests**

Define `TaskType` as a string enum with `CODE_QA`, `TRACE_CHAIN`, and `CHANGE_PLAN`. Test English and Chinese examples, whitespace rejection, fallback to `CODE_QA`, and precedence:

```python
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Where is getAlert implemented?", TaskType.CODE_QA),
        ("告警趋势图的数据从哪里来？", TaskType.TRACE_CHAIN),
        ("Add risk_score; which files need changes?", TaskType.CHANGE_PLAN),
        (
            "修改前后端调用链需要改哪些文件？",
            TaskType.CHANGE_PLAN,
        ),
        ("Explain AlertController", TaskType.CODE_QA),
    ],
)
def test_plan_classifies_question(question, expected):
    assert SimpleAgentPlanner().plan(question) is expected
```

- [x] **Step 2: Run tests and observe RED**

```cmd
.venv\python.exe -m pytest tests\unit\test_agent_planner.py -v
```

Expected: collection fails because `app.agent.planner` does not exist.

- [x] **Step 3: Implement deterministic priority rules**

Use normalized lowercase text and immutable keyword groups. Check change-plan keywords first, trace keywords second, then code-QA keywords/fallback. Raise `ValueError("question must not be blank")` for blank input. Do not call an LLM.

- [x] **Step 4: Add the inspection script**

Support:

```cmd
.venv\python.exe -m scripts.classify_agent_question "新增 risk_score 需要改哪些文件？"
```

Expected output:

```text
Task type: CHANGE_PLAN
```

- [x] **Step 5: Run focused and regression tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_agent_planner.py
.venv\python.exe -m pytest
```

- [x] **Step 6: User manual test gate**

Ask the user to run the script with one location question, one chain question, and one modification question. Stop until all three classifications are approved.

- [ ] **Step 7: Commit and push after approval**

```cmd
git add backend/app/agent backend/scripts/classify_agent_question.py backend/tests/unit/test_agent_planner.py
git commit -m "feat: add deterministic agent planner"
git push
```

---

### Task 2: Implement `ToolRegistry` and `AgentExecutor` (Day 23)

**Files:**
- Create: `backend/app/agent/tool_registry.py`
- Create: `backend/app/agent/executor.py`
- Modify: `backend/app/agent/types.py`
- Create: `backend/tests/unit/test_tool_registry.py`
- Create: `backend/tests/unit/test_agent_executor.py`

- [x] **Step 1: Write failing registry tests**

Require unique nonblank names, callable values, deterministic names, and explicit unknown-tool errors:

```python
registry = ToolRegistry()
registry.register("hybrid_search", fake_search)
assert registry.get("hybrid_search") is fake_search
assert registry.names == ("hybrid_search",)
```

Duplicate registration must raise `ValueError`; unknown lookup must raise:

```python
DomainError(
    code="AGENT_TOOL_NOT_FOUND",
    message="Agent tool 'missing' is not registered.",
    status_code=500,
)
```

- [x] **Step 2: Define a unified internal result and write executor tests**

`AgentResult` contains:

```python
task_type: TaskType
answer: str
references: tuple[ContextReferenceRead, ...] = ()
graph_nodes: tuple[GraphNodeRead, ...] = ()
graph_edges: tuple[GraphEdgeRead, ...] = ()
uncertainties: tuple[str, ...] = ()
```

Use fake code-QA, trace, and change-plan services. Verify exact routing, forwarded `project_id/question/limit`, `max_depth=2` for trace, normalization into immutable tuples, and `AGENT_TASK_UNSUPPORTED` for an invalid task.

- [x] **Step 3: Run tests and observe RED**

```cmd
.venv\python.exe -m pytest tests\unit\test_tool_registry.py tests\unit\test_agent_executor.py -v
```

- [x] **Step 4: Implement the registry and executor**

The executor receives the three focused services through its constructor. It must call existing service methods rather than reimplement search, context construction, or prompting.

- [x] **Step 5: Run focused and full backend tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_tool_registry.py tests\unit\test_agent_executor.py
.venv\python.exe -m pytest
```

- [x] **Step 6: User manual test gate**

Ask the user to run the two focused test files with `-v` and verify that all three routing cases are listed as passed. This task has no public API yet.

- [ ] **Step 7: Commit and push after approval**

```cmd
git add backend/app/agent backend/tests/unit/test_tool_registry.py backend/tests/unit/test_agent_executor.py
git commit -m "feat: route agent tasks through typed tools"
git push
```

---

### Task 3: Implement grounded `ChangePlanService` (Day 24)

**Files:**
- Create: `backend/app/services/change_plan_service.py`
- Modify: `backend/app/schemas/agent.py`
- Create: `backend/tests/unit/test_change_plan_service.py`

- [x] **Step 1: Define structured change-plan contracts**

Add:

```python
class AffectedFileRead(BaseModel):
    entity_id: int
    file_path: str
    reason: str
    suggested_changes: list[str]

class ChangePlanResponse(BaseModel):
    answer: str
    affected_files: list[AffectedFileRead]
    references: list[ContextReferenceRead]
    graph_nodes: list[GraphNodeRead]
    graph_edges: list[GraphEdgeRead]
    uncertainties: list[str]
```

The LLM JSON payload uses `summary`, `affected_files`, `risks`, and `uncertainties`. Every affected file includes an `entity_id`.

- [x] **Step 2: Write failing service tests with fake collaborators**

Cover:

- hybrid results become graph seeds;
- related entities are included once;
- context and prompt include file paths, entities, and stored relations;
- no retrieval evidence returns a deterministic no-support response without invoking the LLM;
- valid JSON maps into `ChangePlanResponse`;
- an affected file whose entity ID or path is not in evidence is removed and recorded as uncertainty;
- malformed JSON raises `CHANGE_PLAN_RESPONSE_INVALID` with status 502;
- unexpected LLM failure becomes `LLM_REQUEST_FAILED`;
- source references remain available even if the model omits them.

- [x] **Step 3: Run tests and observe RED**

```cmd
.venv\python.exe -m pytest tests\unit\test_change_plan_service.py -v
```

- [x] **Step 4: Implement evidence gathering and one-call generation**

Inject a hybrid-search-compatible object, `GraphQueryService`, `GraphContextBuilder`, and `LlmClient`. Search once, expand at most two hops, construct bounded context, and make at most one LLM call.

The system prompt must require JSON and state:

```text
Use only supplied indexed-code evidence.
Never name a file or entity absent from the evidence.
Describe a modification plan; do not generate a patch.
Put unsupported assumptions in uncertainties.
```

Validate the returned entity ID/path pairs against retrieved graph and search evidence before constructing the response.

- [x] **Step 5: Run focused and regression tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_change_plan_service.py
.venv\python.exe -m pytest
```

- [x] **Step 6: User manual test gate**

No paid call is needed. Ask the user to run the focused fake-LLM tests with `-v` and inspect the grounded-file and invented-file rejection cases.

- [ ] **Step 7: Commit and push after approval**

```cmd
git add backend/app/services/change_plan_service.py backend/app/schemas/agent.py backend/tests/unit/test_change_plan_service.py
git commit -m "feat: add grounded change planning"
git push
```

---

### Task 4: Add minimal conversation persistence

**Files:**
- Create: `backend/app/models/conversation.py`
- Create: `backend/app/models/message.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/project.py`
- Create: `backend/app/services/conversation_service.py`
- Modify: `backend/tests/unit/test_models.py`
- Create: `backend/tests/unit/test_conversation_service.py`

- [x] **Step 1: Write failing model tests**

Require:

- `Conversation(project_id, title)` with timestamps;
- `Message(conversation_id, role, content, task_type, metadata_json)`;
- role constraint permits only `user` and `assistant`;
- deleting a project cascades to conversations and messages;
- deleting a conversation cascades to messages;
- messages are ordered by `(created_at, id)`.

- [x] **Step 2: Write failing service tests**

Test `ConversationService` methods:

```python
create(project_id: int, title: str) -> Conversation
get_for_project(conversation_id: int, project_id: int) -> Conversation
save_exchange(
    project_id: int,
    question: str,
    result: AgentResult,
    conversation_id: int | None,
) -> tuple[Conversation, Message]
get_history(conversation_id: int) -> Conversation
```

Cover missing project, missing conversation, project mismatch, title derived from the first 80 question characters, JSON-safe response metadata, atomic user/assistant insertion, and rollback on flush failure.

- [x] **Step 3: Run tests and observe RED**

```cmd
.venv\python.exe -m pytest tests\unit\test_models.py tests\unit\test_conversation_service.py -v
```

- [x] **Step 4: Implement models and persistence**

Use SQLAlchemy relationships and `CheckConstraint("role IN ('user', 'assistant')")`. Store assistant references, graph nodes, graph edges, and uncertainties in `metadata_json`; do not store prompts or credentials.

`save_exchange` must own one transaction and return the persisted conversation plus assistant message. It must not call an LLM.

- [x] **Step 5: Run focused and full backend tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_models.py tests\unit\test_conversation_service.py
.venv\python.exe -m pytest
```

- [x] **Step 6: User manual test gate**

Ask the user to run the focused tests with `-v`. Explain that the test database is temporary and verify the cascade, ordering, mismatch, and rollback cases before approval.

- [ ] **Step 7: Commit and push after approval**

```cmd
git add backend/app/models backend/app/services/conversation_service.py backend/tests/unit/test_models.py backend/tests/unit/test_conversation_service.py
git commit -m "feat: persist agent conversations"
git push
```

---

### Task 5: Expose unified Agent chat and conversation APIs (Day 25)

**Files:**
- Create: `backend/app/services/agent_chat_service.py`
- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/api/agent_api.py`
- Modify: `backend/app/core/dependencies.py`
- Create: `backend/tests/unit/test_agent_chat_service.py`
- Create: `backend/tests/integration/test_agent_chat_api.py`

- [ ] **Step 1: Define HTTP schemas**

Add `AgentChatRequest`, `AgentChatResponse`, `ConversationRead`, and `MessageRead`.

```python
class AgentChatRequest(BaseModel):
    project_id: int
    question: str = Field(min_length=1)
    conversation_id: int | None = None
    limit: int = Field(default=5, ge=1, le=20)

class AgentChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    task_type: TaskType
    answer: str
    references: list[ContextReferenceRead]
    graph_nodes: list[GraphNodeRead]
    graph_edges: list[GraphEdgeRead]
    uncertainties: list[str]
```

- [ ] **Step 2: Write failing orchestration tests**

Verify:

1. planner receives only the current question;
2. executor receives the selected task and request values;
3. history is not read before executor invocation;
4. successful result is persisted;
5. executor failure writes no messages;
6. a supplied conversation is project-validated;
7. the API response uses the persisted assistant message ID.

- [ ] **Step 3: Write failing endpoint tests**

Test:

```http
POST /api/agent/chat
GET  /api/agent/conversations/{conversation_id}
```

Override `get_agent_chat_service` with a fake for routing tests. Add database-backed integration coverage for new conversation, continued conversation, chronological reload, 404, 409 project mismatch, blank question, and invalid limit.

- [ ] **Step 4: Implement service and dependency graph**

Build one request-scoped hybrid search and graph service, then compose code-QA, trace, and change-plan services into `AgentExecutor`. Register `hybrid_search`, `graph_search`, `read_entity`, and `get_related_entities` in `ToolRegistry`.

`AgentChatService.answer()` performs:

```text
validate project/conversation
-> planner.plan(current question)
-> executor.execute(...)
-> conversation_service.save_exchange(...)
-> AgentChatResponse
```

- [ ] **Step 5: Implement endpoints and error mapping**

Keep `/api/agent/code-qa` and `/api/agent/trace` unchanged. Add chat and conversation read routes to the same router.

- [ ] **Step 6: Run focused and full backend tests**

```cmd
.venv\python.exe -m pytest tests\unit\test_agent_chat_service.py tests\integration\test_agent_chat_api.py
.venv\python.exe -m pytest
```

- [ ] **Step 7: User manual API gate**

Start the backend and give the user CMD `curl.exe` commands that use a fake-safe or already configured local environment to:

1. create a chat with `conversation_id` omitted;
2. copy the returned ID into a second chat;
3. fetch the conversation;
4. verify four saved messages in chronological order.

If a real LLM would be used, first confirm all offline tests passed and tell the user the command will consume tokens. One real call is sufficient for this task; continuation may be checked with a mocked/local test route instead.

- [ ] **Step 8: Commit and push after approval**

```cmd
git add backend/app/agent backend/app/services backend/app/schemas/agent.py backend/app/api/agent_api.py backend/app/core/dependencies.py backend/tests/unit/test_agent_chat_service.py backend/tests/integration/test_agent_chat_api.py
git commit -m "feat: expose unified agent chat API"
git push
```

---

### Task 6: Build frontend routing, project management, and search (Day 27)

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/router.ts`
- Create: `frontend/src/components/AppNav.vue`
- Create: `frontend/src/api/projects.ts`
- Create: `frontend/src/api/search.ts`
- Create: `frontend/src/types/project.ts`
- Create: `frontend/src/types/search.ts`
- Create: `frontend/src/views/ProjectView.vue`
- Create: `frontend/src/views/SearchView.vue`
- Create: `frontend/src/views/__tests__/ProjectView.spec.ts`
- Create: `frontend/src/views/__tests__/SearchView.spec.ts`
- Create: `frontend/src/__tests__/router.spec.ts`

- [ ] **Step 1: Install Vue Router**

After obtaining network permission if needed:

```cmd
cd frontend
npm install vue-router@4
```

- [ ] **Step 2: Write failing router and view tests**

Require routes `/projects`, `/search`, and `/graph`, with `/` redirecting to `/projects`. The `/chat` route is added with its real component in Task 7, avoiding a temporary page that would immediately be replaced.

Project tests cover:

- required name and root path;
- project registration;
- scan action;
- refreshed file/line/API/entity statistics;
- loading and API-error states.

Search tests cover:

- required project ID and query;
- `/api/search/hybrid` request body;
- loading, error, empty, and result states;
- file path, line range, entity type, qualified name, score, and source.

- [ ] **Step 3: Run tests and observe RED**

```cmd
npm test -- --run src/__tests__/router.spec.ts src/views/__tests__/ProjectView.spec.ts src/views/__tests__/SearchView.spec.ts
```

- [ ] **Step 4: Implement API modules and views**

Use Axios modules with typed request/response contracts. Keep state local to each view; do not add Pinia. `App.vue` renders `AppNav` and `RouterView`. Preserve `GraphView` as `/graph`.

- [ ] **Step 5: Run frontend tests and build**

```cmd
npm test -- --run
npm run build
```

- [ ] **Step 6: User manual frontend gate**

Ask the user to start backend and frontend, open the page manually, then verify:

1. all four navigation links change routes;
2. Project page can register/scan and show stats;
3. Search page returns hybrid results;
4. existing Graph page still works.

Do not use browser automation or visual inspection unless separately permitted.

- [ ] **Step 7: Commit and push after approval**

```cmd
git add frontend
git commit -m "feat: add project and search frontend routes"
git push
```

---

### Task 7: Build `AgentChat` and reference details (Day 26)

**Files:**
- Create: `frontend/src/api/agent.ts`
- Create: `frontend/src/types/agent.ts`
- Create: `frontend/src/components/ReferenceDialog.vue`
- Create: `frontend/src/views/AgentChat.vue`
- Create: `frontend/src/components/__tests__/ReferenceDialog.spec.ts`
- Create: `frontend/src/views/__tests__/AgentChat.spec.ts`
- Modify: `frontend/src/router.ts`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Write failing chat tests**

Mock the Agent API and test:

- blank questions cannot submit;
- five demo questions populate the input;
- first request omits `conversation_id`;
- later request uses the returned ID;
- answer and task type render;
- references show file paths and line ranges;
- clicking a reference opens code content in `ReferenceDialog`;
- graph data renders through `GraphPanel`;
- uncertainties render for change plans;
- loading, API error, and empty evidence states;
- loading a conversation restores messages;
- restored message content is displayed but is not added to a new request payload.
- router navigation to `/chat` renders `AgentChat`.

- [ ] **Step 2: Run tests and observe RED**

```cmd
npm test -- --run src/components/__tests__/ReferenceDialog.spec.ts src/views/__tests__/AgentChat.spec.ts
```

- [ ] **Step 3: Implement Agent API and types**

Mirror backend schemas exactly. `sendChat()` posts the current question only. `getConversation()` reads stored messages and their metadata.

- [ ] **Step 4: Implement `ReferenceDialog` and `AgentChat`**

The five demo questions are the stable scenarios from `plan.md`. Reuse `GraphPanel`; do not create another graph implementation. Keep the current `conversation_id` in component state and expose a numeric field/button for restoring a saved conversation. Add the real `/chat` route to `router.ts`.

- [ ] **Step 5: Run all frontend checks**

```cmd
npm test -- --run
npm run build
```

- [ ] **Step 6: User manual Agent UI gate**

Ask the user to test `/chat` manually:

1. click a demo question;
2. submit it;
3. inspect task type, answer, and references;
4. open a reference detail;
5. verify graph display for a trace result;
6. reload a saved conversation by ID.

Use at most one real MiMo call after offline tests pass. Additional paid calls require a concrete reason and the user's decision.

- [ ] **Step 7: Commit and push after approval**

```cmd
git add frontend/src
git commit -m "feat: add unified agent chat interface"
git push
```

---

### Task 8: Add Week 4 offline acceptance coverage

**Files:**
- Create: `backend/tests/integration/test_week4_acceptance.py`
- Create: `backend/scripts/show_conversation.py`
- Modify: `backend/README.md`
- Modify: `.env.example` only if a required variable is missing

- [ ] **Step 1: Write the end-to-end offline acceptance test**

Using temporary SQLite, deterministic retrieval/graph fixtures, and a fake LLM:

1. register and scan the sample project;
2. build or fake the index without downloads;
3. ask a code-location question through Agent chat;
4. ask a trace question through Agent chat;
5. ask a change-plan question through Agent chat;
6. assert planner task types;
7. assert references/graph/uncertainties remain grounded;
8. reload each conversation;
9. assert no history text appeared in any fake-LLM prompt;
10. assert project isolation and rollback after injected failure.

- [ ] **Step 2: Implement the CMD inspection script**

Support:

```cmd
.venv\python.exe -m scripts.show_conversation 1
```

Print conversation/project IDs followed by chronological role, task type, content, reference count, graph counts, and uncertainties. Never invoke an LLM.

- [ ] **Step 3: Run acceptance and full backend verification**

```cmd
.venv\python.exe -m pytest tests\integration\test_week4_acceptance.py -v
.venv\python.exe -m pytest
.venv\python.exe -m pytest --cov=app --cov-report=term-missing
.venv\python.exe -m compileall -q app scripts tests
```

Expected: all pass, coverage remains at least 80%, compilation succeeds, and no network/model call occurs.

- [ ] **Step 4: Run complete frontend verification**

```cmd
cd ..\frontend
npm test -- --run
npm run build
```

- [ ] **Step 5: User manual offline gate**

Ask the user to run `test_week4_acceptance.py` and `show_conversation`. Confirm that all three task types and persisted messages appear correctly without spending LLM tokens.

- [ ] **Step 6: Commit and push after approval**

```cmd
git add backend/tests/integration/test_week4_acceptance.py backend/scripts/show_conversation.py backend/README.md .env.example
git commit -m "test: add week 4 offline acceptance coverage"
git push
```

---

### Task 9: Complete documentation and final four-week acceptance (Day 28)

**Files:**
- Create: `README.md` if the repository root README does not exist; otherwise modify it
- Modify: `backend/README.md`
- Modify: `docs/superpowers/plans/2026-07-05-week4-unified-agent-demo.md`

- [ ] **Step 1: Document the complete application**

Include:

- project purpose and four-week architecture;
- prerequisites and CMD setup commands;
- backend/frontend startup;
- environment variables with blank API-key examples;
- project scan and vector-index preparation;
- core API list and `curl.exe` examples;
- `/projects`, `/search`, `/graph`, `/chat`;
- five stable demo questions;
- saved-conversation behavior;
- current limitations and future context-aware follow-up plan;
- token-cost warning for real LLM calls;
- troubleshooting for PowerShell `curl` alias versus `curl.exe`.

- [ ] **Step 2: Run repository hygiene checks**

```cmd
git status --short
git ls-files | findstr /i ".env .venv node_modules dist qdrant_data research_code_agent.db"
```

Expected: no credential file, virtual environment, model cache, database, Qdrant data, `node_modules`, or build output is tracked.

- [ ] **Step 3: Run final backend verification from the Week 4 worktree**

```cmd
cd backend
.venv\python.exe -m pytest
.venv\python.exe -m pytest --cov=app --cov-report=term-missing
.venv\python.exe -m compileall -q app scripts tests
```

- [ ] **Step 4: Run final frontend verification**

```cmd
cd ..\frontend
npm test -- --run
npm run build
```

- [ ] **Step 5: User final manual acceptance gate**

The user manually verifies:

1. a real project can be registered, scanned, and counted;
2. natural-language search returns code;
3. the code-location demo returns cited files and lines;
4. the trace demo returns frontend → API → controller → service where evidence exists;
5. the frontend-interface demo returns frontend files and APIs;
6. the algorithm demo returns a Python function and file;
7. the `risk_score` change demo returns grounded files, suggestions, and uncertainties;
8. the Agent UI is operable;
9. a saved conversation reloads but does not affect a later LLM prompt.

One representative real-MiMo call may be used only after all offline checks pass. The remaining scenarios should prefer deterministic fixture/fake validation unless the user explicitly chooses to spend additional tokens.

The user captures screenshots manually if desired. Do not invoke browser/visual tools without explicit permission.

- [ ] **Step 6: Commit and push Week 4 after approval**

```cmd
git add README.md backend/README.md docs/superpowers/plans/2026-07-05-week4-unified-agent-demo.md
git commit -m "docs: complete ResearchCode Agent MVP guide"
git push
```

- [ ] **Step 7: Merge only on separate instruction**

After the isolated branch is fully clean and pushed, explain the verification evidence and wait for explicit permission before merging to `main`, testing the main worktree, and pushing `origin/main`.

---

## Checkpoints

| Checkpoint | Task | User-visible result |
| --- | --- | --- |
| A | 1 | Questions deterministically classify into three task types |
| B | 2 | Typed registry and executor route each task correctly |
| C | 3 | Change planning returns grounded files and rejects inventions |
| D | 4 | Conversations and messages persist atomically |
| E | 5 | One chat API handles all tasks and reloads conversations |
| F | 6 | Project, search, graph, and chat routes are available |
| G | 7 | Agent chat displays answers, citations, graphs, and uncertainties |
| H | 8 | Full Week 4 flow passes offline without paid calls |
| I | 9 | Documentation and final four-week acceptance are complete |

Every checkpoint is a mandatory stop. The user's manual approval authorizes only that task's commit and push to the isolated Week 4 branch.

## Definition of done

- [ ] Planner distinguishes `CODE_QA`, `TRACE_CHAIN`, and `CHANGE_PLAN` deterministically.
- [ ] Tool registry exposes the four planned tools with explicit lookup failures.
- [ ] Executor reuses code-QA, trace, and change-plan services and normalizes results.
- [ ] Change plans contain only retrieved files/entities and identify uncertainty.
- [ ] `/api/agent/chat` supports all three tasks.
- [ ] Conversations save both messages atomically and can be reloaded.
- [ ] Stored messages never enter the LLM context.
- [ ] Existing `/api/agent/code-qa` and `/api/agent/trace` remain compatible.
- [ ] Frontend routes `/projects`, `/search`, `/graph`, and `/chat` all work.
- [ ] Chat renders task type, answer, references, graph, and uncertainties.
- [ ] Five stable demo questions are documented and available in the UI.
- [ ] Backend tests, coverage, and compileall pass.
- [ ] Frontend tests, type checking, and production build pass.
- [ ] Automated verification makes no real embedding or LLM request.
- [ ] README documents startup, APIs, demo, limitations, and token-cost precautions.
- [ ] User approves every task before its commit/push.
- [ ] User approves the final branch before any merge to `main`.

## Self-audit against `plan.md` and the approved design

- Day 22 is Task 1.
- Day 23 is Task 2 and the dependency composition in Task 5.
- Day 24 is Task 3.
- Day 25 is Tasks 4 and 5.
- Day 26 is Task 7.
- Day 27 is Task 6.
- Day 28 is Tasks 8 and 9.
- The five mandatory demo scenarios are included in Task 7 and final acceptance.
- Minimal conversation persistence is implemented and observable through reload.
- Context-aware follow-up is explicitly deferred and documented as future work.
- High-token visual tools and repeated real-LLM calls remain permission-gated.
