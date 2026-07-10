# Same-Conversation Working Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Agent chat turn use a bounded, project-isolated window of its existing conversation as working memory for follow-up questions.

**Architecture:** `ConversationService` will format the latest persisted messages from a validated conversation into a bounded text block. `AgentChatService` will load this block before dispatching a follow-up, while the deterministic planner still receives only the current question. `AgentExecutor` passes the block to the selected task service, which augments its retrieval and LLM prompt without treating prior assistant output as authoritative code evidence.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Pydantic, pytest.

---

### Task 1: Define bounded conversation-memory formatting

**Files:**
- Create: `backend/app/services/conversation_memory.py`
- Test: `backend/tests/unit/test_conversation_memory.py`

- [x] **Step 1: Write failing formatter tests**

```python
def test_build_conversation_memory_keeps_only_the_latest_six_messages() -> None:
    memory = build_conversation_memory(messages)
    assert "Question 1" not in memory
    assert "Question 4" in memory

def test_build_conversation_memory_truncates_each_message_and_the_total_output() -> None:
    memory = build_conversation_memory(messages)
    assert len(memory) <= MAX_MEMORY_CHARS
    assert "[truncated]" in memory
```

- [x] **Step 2: Run the formatter tests and confirm they fail because the module does not exist**

Run: `./.venv/python.exe -m pytest tests/unit/test_conversation_memory.py -q`

Expected: collection error for `app.services.conversation_memory`.

- [x] **Step 3: Implement a pure formatter**

```python
MAX_MEMORY_MESSAGES = 6
MAX_MESSAGE_CHARS = 1_000
MAX_MEMORY_CHARS = 4_000

def build_conversation_memory(messages: Sequence[Message]) -> str:
    recent = messages[-MAX_MEMORY_MESSAGES:]
    lines = ["Conversation context (not code evidence):"]
    for message in recent:
        content = _truncate(message.content.strip(), MAX_MESSAGE_CHARS)
        lines.append(f"{message.role.title()}: {content}")
    return _truncate("\n".join(lines), MAX_MEMORY_CHARS)
```

- [x] **Step 4: Run the formatter tests and confirm they pass**

Run: `./.venv/python.exe -m pytest tests/unit/test_conversation_memory.py -q`

Expected: all tests pass.

### Task 2: Load memory only for the validated, current-project conversation

**Files:**
- Modify: `backend/app/services/conversation_service.py:59-129`
- Modify: `backend/app/services/agent_chat_service.py:23-82`
- Test: `backend/tests/unit/test_conversation_service.py`
- Test: `backend/tests/unit/test_agent_chat_service.py`

- [x] **Step 1: Write failing service tests**

```python
def test_get_working_memory_returns_only_existing_messages_for_the_project(...) -> None:
    memory = service.get_working_memory(project.id, conversation.id)
    assert "First question" in memory

def test_answer_passes_existing_conversation_memory_to_executor() -> None:
    service.answer(..., conversation_id=8, ...)
    assert executor.calls[0].conversation_memory == "Conversation context ..."
```

- [x] **Step 2: Run the focused tests and confirm the new APIs are missing**

Run: `./.venv/python.exe -m pytest tests/unit/test_conversation_service.py tests/unit/test_agent_chat_service.py -q`

Expected: failures for missing `get_working_memory` and unsupported `conversation_memory` argument.

- [x] **Step 3: Add retrieval and dispatch wiring**

```python
def get_working_memory(self, project_id: int, conversation_id: int | None) -> str:
    if conversation_id is None:
        return ""
    conversation = self.get_for_project(conversation_id, project_id)
    return build_conversation_memory(conversation.messages)

memory = self.conversations.get_working_memory(project_id, conversation_id)
result = self.executor.execute(..., conversation_memory=memory)
```

Keep validation before planning and do not include the current, unsaved question in memory.

- [x] **Step 4: Run focused tests and confirm they pass**

Run: `./.venv/python.exe -m pytest tests/unit/test_conversation_service.py tests/unit/test_agent_chat_service.py -q`

Expected: all tests pass.

### Task 3: Propagate working memory to retrieval and generation

**Files:**
- Modify: `backend/app/agent/executor.py:7-75`
- Modify: `backend/app/services/code_qa_service.py:54-103`
- Modify: `backend/app/services/trace_service.py:87-197`
- Modify: `backend/app/services/change_plan_service.py:142-304`
- Test: `backend/tests/unit/test_agent_executor.py`
- Test: `backend/tests/unit/test_code_qa_service.py`
- Test: `backend/tests/unit/test_trace_service.py`
- Test: `backend/tests/unit/test_change_plan_service.py`

- [x] **Step 1: Write failing propagation tests**

```python
def test_executor_passes_conversation_memory_to_code_qa() -> None:
    executor.execute(..., conversation_memory="User: Explain alert API")
    assert code_qa.calls[0]["conversation_memory"] == "User: Explain alert API"

def test_code_qa_uses_memory_in_its_retrieval_query_and_prompt() -> None:
    response = service.answer(..., conversation_memory="User: Explain alert API")
    assert "Conversation context" in search.queries[0]
    assert "Conversation context" in llm.user_prompts[0]
```

- [x] **Step 2: Run focused tests and confirm they fail due to missing memory parameters**

Run: `./.venv/python.exe -m pytest tests/unit/test_agent_executor.py tests/unit/test_code_qa_service.py tests/unit/test_trace_service.py tests/unit/test_change_plan_service.py -q`

Expected: failures for unexpected `conversation_memory` arguments or missing context in recorded calls.

- [x] **Step 3: Add an optional `conversation_memory: str = ""` parameter across task service boundaries**

```python
def _question_with_memory(question: str, conversation_memory: str) -> str:
    if not conversation_memory:
        return question
    return f"{conversation_memory}\n\nCurrent question:\n{question}"
```

Use the augmented question for retrieval and LLM prompts. Preserve the original current question for planner routing, persistence, and response semantics. Repair prompts must use the same augmented question so evidence repair preserves conversational intent.

- [x] **Step 4: Run focused tests and confirm they pass**

Run: `./.venv/python.exe -m pytest tests/unit/test_agent_executor.py tests/unit/test_code_qa_service.py tests/unit/test_trace_service.py tests/unit/test_change_plan_service.py -q`

Expected: all tests pass.

### Task 4: Verify regression safety

**Files:**
- Modify: `expert-question-notes/004-same-conversation-working-memory.md` (append-only implementation result)

- [x] **Step 1: Run all backend tests**

Run: `./.venv/python.exe -m pytest -q`

Expected: all tests pass, with any pre-existing skips reported by pytest.

- [x] **Step 2: Compile backend code**

Run: `./.venv/python.exe -m compileall -q app tests`

Expected: exit code 0.

- [x] **Step 3: Inspect the final diff**

Run: `git diff --check`

Expected: exit code 0 with no whitespace errors.

- [x] **Step 4: Append implementation verification results to the expert note**

Record only verified test and compilation results with a timestamp. Do not commit because the user requested local review after implementation.
