# Task 8 Grounded Answer Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent code-QA answers from presenting semantic proximity as an explicit code relationship and from citing tangential retrieval results.

**Architecture:** Keep the existing retrieval, context, and LLM interfaces unchanged. Tighten the system prompt so every relationship claim requires direct evidence in a supplied snippet, and lock those rules with unit tests. Validate the behavior with the same real MiMo question that exposed the defect; defer relationship-graph enrichment unless prompt-level grounding still fails.

**Tech Stack:** Python 3.11, pytest, FastAPI, OpenAI-compatible chat completions, MiMo `mimo-v2.5`

---

## Token-Cost Constraint

Real MiMo calls consume limited paid tokens and are not part of the automated test loop.

- All unit, integration, regression, and acceptance tests must use fake LLM clients.
- Do not call the real `/api/agent/code-qa` endpoint while developing or debugging.
- Run the real MiMo evaluation only after focused tests, the complete test suite, compilation, and `git diff --check` all pass.
- The manual acceptance phase has a default budget of exactly one real LLM request.
- If that request fails its acceptance criteria, analyze the saved response first. Do not retry the real API until a new offline-tested change exists and the user explicitly approves another token-consuming call.
- Never use repeated real calls to tune wording, compare prompt variants, or diagnose code failures.

---

## Root Cause and Scope

The retrieval and citation plumbing are correct: every `[n]` maps to the advertised file and line range. The defect occurs at generation time:

1. `SYSTEM_PROMPT` prohibits invention but does not define the evidence threshold for a relationship claim.
2. Retrieved Controller, Service, and frontend entities appear together, encouraging the model to infer wiring from semantic proximity.
3. The prompt does not tell the model to ignore tangential retrieved blocks, so the answer cites the unrelated POST search call.

This correction does not change hybrid weights, remove valid search hits, add post-generation string filters, or claim that prompt instructions can mathematically eliminate hallucinations.

---

### Task 1: Add a failing grounding-policy regression test

**Files:**
- Modify: `backend/tests/unit/test_code_qa_service.py`
- Test: `backend/tests/unit/test_code_qa_service.py`

- [ ] **Step 1: Extend the prompt assertions**

Add assertions to `test_answers_from_cited_retrieval_context`:

```python
assert (
    "Treat each context block as independent evidence."
    in system_prompt
)
assert (
    "Do not claim that one symbol calls, injects, delegates to, "
    "supports, or is connected to another unless a supplied code "
    "snippet explicitly shows that relationship."
    in system_prompt
)
assert (
    "Distinguish a declaration from an observed call relationship."
    in system_prompt
)
assert (
    "Ignore retrieved blocks that are not needed to answer the question."
    in system_prompt
)
assert (
    "Every citation must directly support the sentence that uses it."
    in system_prompt
)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_code_qa_service.py::test_answers_from_cited_retrieval_context -v
```

Expected: FAIL because the current `SYSTEM_PROMPT` does not contain the new evidence rules.

---

### Task 2: Harden the code-QA system prompt

**Files:**
- Modify: `backend/app/services/code_qa_service.py`
- Test: `backend/tests/unit/test_code_qa_service.py`

- [ ] **Step 1: Replace the system prompt**

Use this prompt:

```python
SYSTEM_PROMPT = """Answer only from the supplied code context.
Cite factual claims with [n].
Every citation must directly support the sentence that uses it.
Treat each context block as independent evidence.
Do not claim that one symbol calls, injects, delegates to, supports, or is connected to another unless a supplied code snippet explicitly shows that relationship.
Distinguish a declaration from an observed call relationship.
Ignore retrieved blocks that are not needed to answer the question.
Do not invent files, symbols, APIs, behavior, or relationships.
If context is insufficient, state exactly what cannot be determined."""
```

- [ ] **Step 2: Run the focused test and verify GREEN**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_code_qa_service.py -v
```

Expected: all code-QA unit tests pass.

- [ ] **Step 3: Run Task 8 integration tests**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_code_qa_api.py -v
```

Expected: all endpoint tests pass without calling MiMo.

---

### Task 3: Verify regressions and repeat the real MiMo evaluation

**Files:**
- No additional source files

- [ ] **Step 1: Run complete automated verification**

Run:

```cmd
.venv\python.exe -m pytest
.venv\python.exe -m compileall -q app tests
git diff --check
git status --short
```

Expected: all tests pass, compilation succeeds, and only intended Task 8 plus correction files are modified.

- [ ] **Step 2: Fully restart Uvicorn**

Stop the existing process with `Ctrl+C`, then run:

```cmd
.venv\python.exe -m uvicorn app.main:app --reload
```

A full restart is required so the updated prompt and cached dependencies are recreated.

- [ ] **Step 3: Repeat the original real-model request**

This is the only planned token-consuming request. Do not run it until every
automated verification in Step 1 passes, and let the user execute it manually.

Run:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/agent/code-qa -H "Content-Type: application/json" -d "{\"project_id\":1,\"question\":\"Where is the alert API implemented?\",\"limit\":5}"
```

Accept the result only if all of these are true:

- it identifies `GET /api/alerts/{id}` and `AlertController.getAlert` with the direct backend API citation;
- it may state that the Controller body currently returns `null`;
- it does not claim `AlertService` supports, is wired to, or is called by the Controller;
- if it mentions `AlertService.findById`, it explicitly says the supplied snippets do not establish a connection;
- it may cite the frontend GET call, but does not use the POST search call as evidence for the GET endpoint;
- every citation directly supports the sentence containing it.

- [ ] **Step 4: Escalate only if the same defect remains**

If MiMo still infers a relationship after the prompt change, do not immediately
retry. Preserve and analyze the response, then stop and create a separate
design for relationship-aware context. That follow-up should use stored
`CodeRelation` rows to label explicit relations and should not be bundled into
this correction without a new test, design review, and explicit user approval
for any additional real-model call.

---

### Task 4: Commit the corrected Task 8 only after manual acceptance

**Files:**
- Include all intended Task 8 source and tests
- Include: `docs/superpowers/plans/2026-07-04-task8-grounded-answer-correction.md`
- Exclude: `backend/.env`

- [ ] **Step 1: Confirm the local credential file is ignored**

Run:

```cmd
git status --short --ignored backend/.env
```

Expected: `backend/.env` is marked ignored and is not staged.

- [ ] **Step 2: Stage, commit, and push after user approval**

Run:

```cmd
git add .gitignore backend/app backend/tests docs/superpowers/plans/2026-07-04-task8-grounded-answer-correction.md
git commit -m "feat: answer grounded code questions"
git push
```

Expected: the Task 8 implementation and grounding correction are pushed to `feature/week2-retrieval-rag`; the API key remains local.
