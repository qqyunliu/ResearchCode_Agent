# Answer Evidence Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight backend guard that blocks Agent answers containing file paths or citation IDs not present in the structured evidence references.

**Architecture:** Add a small `AnswerEvidenceValidator` service that validates answer text against `ContextReferenceRead` values. Use it inside the RAG-backed answer services while they still have the original context, allowing at most one stricter repair LLM call before returning a conservative fallback.

**Tech Stack:** Python 3.11, FastAPI service layer, Pydantic response schemas, pytest.

---

### Task 1: Evidence Validator

**Files:**
- Create: `backend/app/services/evidence_validator.py`
- Test: `backend/tests/unit/test_evidence_validator.py`

- [ ] Write tests for allowed citations/paths, unknown citation IDs, unknown paths, and path line ranges.
- [ ] Implement regex-based extraction for citation IDs and code-like file paths.
- [ ] Return a structured validation result with `is_valid`, `invalid_citations`, `invalid_paths`, and user-facing uncertainty messages.

### Task 2: Code QA One-Shot Repair

**Files:**
- Modify: `backend/app/services/code_qa_service.py`
- Test: `backend/tests/unit/test_code_qa_service.py`

- [ ] Add a test where the first LLM answer contains an unsupported path and the second answer is valid.
- [ ] Add a test where both first and repair answers are invalid and the service returns a conservative failure answer.
- [ ] Implement one repair call using the same context, without re-running search.

### Task 3: Trace and Change Plan Guards

**Files:**
- Modify: `backend/app/services/trace_service.py`
- Modify: `backend/app/services/change_plan_service.py`
- Test: `backend/tests/unit/test_trace_service.py`
- Test: `backend/tests/unit/test_change_plan_service.py`

- [ ] Add focused tests for one-shot trace repair.
- [ ] Add focused tests that invalid change-plan natural-language output is blocked after validation failure.
- [ ] Keep structured references and graph evidence in the response even when the answer text is blocked.

### Task 4: Verification

**Files:**
- All touched backend files.

- [ ] Run focused unit tests for validator and changed services.
- [ ] Run backend compile check.
- [ ] Run the backend unit test suite or a practical focused subset if full suite is slow.
