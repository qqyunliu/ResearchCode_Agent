# Relationship Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make trace/change-plan responses explicitly state missing indexed relationship evidence instead of relying on the LLM to honor prompt-only relationship constraints.

**Architecture:** Keep the lightweight approach. Do not parse arbitrary natural language relationships. Add deterministic relationship-limit text derived from existing `graph_edges`/uncertainties and append it to final answers for trace/change-plan tasks when expected relationship edge types are missing.

**Tech Stack:** Python 3.11, FastAPI service layer, pytest.

---

### Task 1: Trace Relationship Limits

**Files:**
- Modify: `backend/app/services/trace_service.py`
- Test: `backend/tests/unit/test_trace_service.py`

- [ ] Add a failing test where trace graph lacks `REQUESTS_API` and `DEFINES_API`, and final answer must include deterministic relationship limits.
- [ ] Implement a helper that appends an `Indexed relationship limits:` section from existing uncertainty messages.
- [ ] Ensure the helper runs for initial valid answers and repaired valid answers.

### Task 2: Change Plan Relationship Limits

**Files:**
- Modify: `backend/app/services/change_plan_service.py`
- Test: `backend/tests/unit/test_change_plan_service.py`

- [ ] Add a failing test where change-plan graph lacks expected relationship edge types, and final answer must include deterministic relationship limits.
- [ ] Reuse the same wording style as trace.
- [ ] Ensure validation still runs after deterministic text is appended.

### Task 3: Verification

**Files:**
- All touched backend files.

- [ ] Run focused unit tests for trace and change-plan.
- [ ] Run compile check.
- [ ] Run backend pytest suite.
