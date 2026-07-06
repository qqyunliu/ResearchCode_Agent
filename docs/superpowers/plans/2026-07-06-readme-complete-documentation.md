# Complete README Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the root README with an accurate, complete English document for both portfolio readers and developers.

**Architecture:** Keep the documentation in one root `README.md`, starting with project value and architecture before moving into implementation details, setup, API usage, testing, and limitations. Derive every technical claim from the current `main` source, configuration, or tests, and clearly separate implemented behavior from roadmap ideas.

**Tech Stack:** Markdown, FastAPI, SQLAlchemy, SQLite, Qdrant, sentence-transformers/OpenAI-compatible embeddings, OpenAI-compatible chat API, Tree-sitter, Python AST, Vue 3, TypeScript, Cytoscape, pytest, Vitest

---

### Task 1: Verify README source facts

**Files:**
- Read: `backend/app/api/*.py`
- Read: `backend/app/schemas/*.py`
- Read: `backend/app/parsers/*.py`
- Read: `backend/app/services/*.py`
- Read: `backend/app/agent/*.py`
- Read: `backend/app/core/config.py`
- Read: `backend/.env.example`
- Read: `frontend/src/router.ts`
- Read: `frontend/package.json`
- Read: `backend/tests/`
- Read: `frontend/src/**/__tests__/`

- [ ] **Step 1: Inventory endpoints, configuration, entities, relations, routes, and verification commands**

Run:

```powershell
rg -n "@router|class .*Request|class .*Response|RCA_|EntityType|RelationType|path:" backend frontend
```

Expected: the output identifies the implemented public contracts and supported model types without relying on README claims.

- [ ] **Step 2: Confirm repository-relative startup paths**

Run:

```powershell
rg -n "\.worktrees|week4-unified-agent-demo" README.md backend/README.md
```

Expected: stale worktree paths in the existing root README are identified for removal.

### Task 2: Rewrite the root README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the overview and architecture sections**

Write an English introduction, capability list, end-to-end data flow, technology stack, supported languages, parsed entity table, and relation table. State that the planner is deterministic and that registered tools are not currently selected by an LLM function-calling loop.

- [ ] **Step 2: Document retrieval, GraphRAG, and Agent execution**

Describe project-scoped Qdrant collections, keyword/vector score fusion, one/two-hop graph expansion, the three task types, grounded references, change-plan filtering, conversation persistence, and failure behavior.

- [ ] **Step 3: Document repository structure and configuration**

Add a focused directory tree, prerequisites, environment-variable table, local/API embedding options, local/remote Qdrant options, and LLM configuration. Warn that real Agent calls consume provider tokens.

- [ ] **Step 4: Correct installation and startup instructions**

Use commands rooted at:

```text
F:\LIUQINGYUN\ResearchCode_Agent\backend
F:\LIUQINGYUN\ResearchCode_Agent\frontend
```

Do not refer to a feature worktree. Explain the existing Conda-prefix-style `.venv\python.exe` path and the standard virtual-environment alternative.

- [ ] **Step 5: Document workflows, frontend routes, APIs, and scripts**

Include project registration, scan, index, statistics, keyword search, hybrid search, graph query, unified Agent chat, conversation reload, and offline inspection examples. Keep request bodies aligned with Pydantic schemas.

- [ ] **Step 6: Document tests, safeguards, limitations, and roadmap**

List offline deterministic test behavior, backend/frontend verification commands, static-analysis confidence rules, project isolation, evidence boundaries, known parser/runtime limitations, and a clearly labeled non-implemented roadmap.

### Task 3: Validate the documentation

**Files:**
- Verify: `README.md`
- Verify: `docs/superpowers/specs/2026-07-06-readme-complete-documentation-design.md`
- Verify: `docs/superpowers/plans/2026-07-06-readme-complete-documentation.md`

- [ ] **Step 1: Check Markdown whitespace and patch integrity**

Run:

```powershell
git diff --check
```

Expected: exit code `0` and no whitespace errors.

- [ ] **Step 2: Check for stale paths and unsupported terminology**

Run:

```powershell
rg -n "\.worktrees|week4-unified-agent-demo|autonomous tool|document retrieval|hundreds of thousands" README.md
```

Expected: no stale paths or unsupported capability claims.

- [ ] **Step 3: Cross-check documented endpoints**

Run:

```powershell
rg -n "POST /api|GET  /api|GET /api" README.md
rg -n "@router\.(get|post)" backend/app/api
```

Expected: every README endpoint maps to an implemented router endpoint.

- [ ] **Step 4: Review the final diff**

Run:

```powershell
git diff -- README.md
git status --short
```

Expected: the README rewrite and the two supporting documentation files are the only intended changes.

- [ ] **Step 5: Request confirmation before commit and push**

Do not commit or push automatically. Present the verified diff summary and ask the user for separate confirmation, because the work is being performed directly on `main`.
