# Project History Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Projects page into a complete history workspace with selection, filtering, pagination, persistent drag ordering, safe cascade deletion, path checks, and project-aware shortcuts.

**Architecture:** `GET /api/projects` returns the complete manually ordered collection and the Vue page performs client-side filtering, temporary sorting, and pagination. SQLite persists `sort_order` through a small idempotent compatibility migration; Qdrant cleanup and database cascades are coordinated by `ProjectService`. Search, Graph, and Agent only gain positive `project_id` query-prefill behavior.

**Tech Stack:** FastAPI, SQLAlchemy 2, SQLite, Qdrant Client, Pydantic 2, Vue 3 Composition API, Vue Router, Axios, Vitest, pytest

---

## Execution boundaries

- Work directly on the current `main` workspace as previously requested.
- Follow red-green-refactor for every behavior change.
- Do not call real LLM or Embedding APIs.
- Do not use browser-driven visual inspection without separate permission.
- Do not commit or push after automation succeeds. Deliver the manual test
  checklist first and wait for the user's explicit commit confirmation.

### Task 1: Add the persistent project order and compatibility migration

**Files:**
- Create: `backend/app/core/schema_migrations.py`
- Modify: `backend/app/models/project.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_schema_migrations.py`
- Test: `backend/tests/unit/test_models.py`

- [ ] **Step 1: Write failing model and migration tests**

Add tests proving that a fresh `Project` has an integer `sort_order`, and that
`upgrade_schema(engine)` adds/backfills the column in a legacy SQLite database
without changing existing IDs, names, or paths. Run the migration twice in the
same test to prove idempotency.

```python
upgrade_schema(engine)
upgrade_schema(engine)
rows = connection.execute(
    text("SELECT id, name, sort_order FROM projects ORDER BY sort_order")
).all()
assert rows == [(2, "Newer", 0), (1, "Older", 1)]
```

- [ ] **Step 2: Run the focused tests and verify the expected failures**

Run:

```powershell
.\.venv\python.exe -m pytest tests/unit/test_schema_migrations.py tests/unit/test_models.py -q
```

Expected: failures because `sort_order` and `upgrade_schema` do not exist.

- [ ] **Step 3: Implement the minimal migration**

Add `sort_order` to `Project`:

```python
sort_order: Mapped[int] = mapped_column(
    Integer,
    default=0,
    nullable=False,
)
```

Implement `upgrade_schema(engine)` using SQLAlchemy inspection and a transaction.
For SQLite, issue `ALTER TABLE projects ADD COLUMN sort_order INTEGER NOT NULL
DEFAULT 0`, then assign `0..n-1` in descending `created_at`, descending `id`
order. Do nothing when the table or column does not yet exist.

Call `upgrade_schema(engine)` before `Base.metadata.create_all(bind=engine)` in
the application lifespan.

- [ ] **Step 4: Run the focused tests**

Expected: all model and migration tests pass.

### Task 2: Add list and reorder domain behavior

**Files:**
- Modify: `backend/app/schemas/project.py`
- Modify: `backend/app/services/project_service.py`
- Modify: `backend/app/api/project_api.py`
- Modify: `backend/tests/integration/test_projects_api.py`

- [ ] **Step 1: Write failing API tests**

Cover:

- list results use manual order;
- list fields include timestamps, order, status, and `path_accessible`;
- existing/missing directories report `true`/`false`;
- a new project becomes first;
- reorder accepts every ID exactly once;
- duplicates, omissions, and unknown IDs return
  `409 PROJECT_ORDER_CONFLICT`;
- a list request after reorder preserves the saved order.

Use temporary directories and remove one after creating its database project to
test an inaccessible historical path.

- [ ] **Step 2: Run the focused API tests and verify RED**

```powershell
.\.venv\python.exe -m pytest tests/integration/test_projects_api.py -q
```

Expected: `GET /api/projects` and `PUT /api/projects/order` fail or return
method-not-allowed.

- [ ] **Step 3: Add explicit request/response schemas**

Add:

```python
class ProjectListItem(ProjectRead):
    created_at: datetime
    last_scan_at: datetime | None
    sort_order: int
    path_accessible: bool

class ProjectOrderUpdate(BaseModel):
    project_ids: list[int] = Field(min_length=1)
```

Keep path accessibility computed at response time; do not persist it because
filesystem availability can change independently of the database.

- [ ] **Step 4: Implement list, create-at-front, and reorder**

Add service methods with these contracts:

```python
def list_projects(self) -> list[Project]: ...
def reorder(self, project_ids: list[int]) -> list[Project]: ...
```

Before creating a project, increment every current `sort_order`, then create the
new row at `0` in the same transaction. Reorder must compare
`len(ids) == len(set(ids))` and `set(ids) == set(database_ids)` before assigning
enumerated order values and committing.

Add routes in this order so `/{project_id}` cannot shadow `/order`:

```python
@router.get("", response_model=list[ProjectListItem])
@router.put("/order", response_model=list[ProjectListItem])
```

Map `Path(project.root_path).is_dir()` to `path_accessible`.

- [ ] **Step 5: Run focused tests and the existing scan API tests**

```powershell
.\.venv\python.exe -m pytest tests/integration/test_projects_api.py tests/integration/test_scan_api.py -q
```

Expected: all selected tests pass.

### Task 3: Add safe project and Qdrant deletion

**Files:**
- Modify: `backend/app/retrieval/vector_store.py`
- Modify: `backend/app/core/dependencies.py`
- Modify: `backend/app/services/project_service.py`
- Modify: `backend/app/api/project_api.py`
- Modify: `backend/tests/integration/test_vector_store.py`
- Modify: `backend/tests/integration/test_projects_api.py`

- [ ] **Step 1: Write failing vector-store and API tests**

Cover:

- `delete_project_collection(id)` deletes an existing collection;
- a missing collection is a successful no-op;
- deleting a project removes its files, entities, relations, issues,
  conversations, and messages;
- missing project returns `404 PROJECT_NOT_FOUND`;
- vector-store failure returns `502 VECTOR_STORE_DELETE_FAILED` and leaves the
  database row and dependents intact.

Override `get_vector_store` in API tests with a deterministic fake; do not open
the configured real Qdrant storage.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
.\.venv\python.exe -m pytest tests/integration/test_vector_store.py tests/integration/test_projects_api.py -q
```

- [ ] **Step 3: Implement Qdrant deletion**

```python
def delete_project_collection(self, project_id: int) -> None:
    name = self.collection_name(project_id)
    if self._client.collection_exists(name):
        self._client.delete_collection(name)
```

- [ ] **Step 4: Implement service and route deletion**

Inject `QdrantVectorStore` through `Depends(get_vector_store)`. Locate the
project before touching Qdrant. Sanitize vector-store exceptions into:

```python
DomainError(
    code="VECTOR_STORE_DELETE_FAILED",
    message="Unable to delete the project's vector index.",
    status_code=502,
)
```

After Qdrant succeeds, call `session.delete(project)` and commit. Add:

```python
@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 5: Run focused deletion and conversation tests**

```powershell
.\.venv\python.exe -m pytest tests/integration/test_projects_api.py tests/integration/test_vector_store.py tests/unit/test_conversation_service.py -q
```

Expected: all selected tests pass and no real Qdrant/LLM call occurs.

### Task 4: Add frontend API contracts

**Files:**
- Modify: `frontend/src/types/project.ts`
- Modify: `frontend/src/api/projects.ts`
- Test: `frontend/src/views/__tests__/ProjectView.spec.ts`

- [ ] **Step 1: Extend the hoisted API mock and write failing contract-facing view tests**

Add mocks for:

```typescript
listProjects: vi.fn(),
reorderProjects: vi.fn(),
deleteProject: vi.fn(),
```

Start with a load test asserting that mounting the view calls `listProjects()`
and renders returned names. Configure `listProjects` in `beforeEach` so existing
tests do not perform undefined mock work.

- [ ] **Step 2: Run the ProjectView suite and verify RED**

```powershell
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
```

- [ ] **Step 3: Add frontend types and API functions**

Define:

```typescript
export interface Project {
  id: number
  name: string
  root_path: string
  status: "created" | "scanning" | "ready" | "failed"
  created_at: string
  last_scan_at: string | null
  sort_order: number
  path_accessible: boolean
}
```

Add Axios wrappers:

```typescript
listProjects(): Promise<Project[]>
reorderProjects(projectIds: number[]): Promise<Project[]>
deleteProject(projectId: number): Promise<void>
```

- [ ] **Step 4: Run type checking and the focused suite**

```powershell
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
npm.cmd run build
```

The view test may remain red only for UI not yet implemented; TypeScript must
compile without API/type errors.

### Task 5: Build the history list, selection, filtering, sorting, and pagination

**Files:**
- Create: `frontend/src/components/ProjectHistoryList.vue`
- Create: `frontend/src/components/__tests__/ProjectHistoryList.spec.ts`
- Modify: `frontend/src/views/ProjectView.vue`
- Modify: `frontend/src/views/__tests__/ProjectView.spec.ts`

- [ ] **Step 1: Write failing component tests**

Cover:

- loading, empty-list, and no-filter-match states;
- selected item marker and emitted selection;
- case-insensitive name/path filtering;
- manual, ID, name, and last-scan sorting;
- configurable page size and page navigation;
- path/status labels and complete path title;
- refresh event;
- field sorting never mutates canonical manual order.

- [ ] **Step 2: Run the component tests and verify RED**

```powershell
npm.cmd test -- --run src/components/__tests__/ProjectHistoryList.spec.ts
```

- [ ] **Step 3: Implement the isolated history component**

The component receives `projects`, `selectedProjectId`, and `loading`, owns
display-only filter/sort/page state, and emits `select`, `refresh`, and
`begin-reorder`. Keep all network calls in `ProjectView`.

- [ ] **Step 4: Write failing ProjectView selection tests**

Assert initial selection, selection-driven statistics loading, stale state
clearing, inaccessible-path scan disabling, refresh behavior, and registration
insertion/selection. For a duplicate create error with
`response.data.detail.code === "PROJECT_ROOT_EXISTS"`, assert refresh and
selection by normalized root path.

- [ ] **Step 5: Integrate the two-column workspace**

Refactor `ProjectView` state to:

```typescript
const projects = ref<Project[]>([])
const selectedProjectId = ref<number | null>(null)
const selectedProject = computed(...)
```

Load projects in `onMounted`. Keep selected-operation state keyed to the current
project ID so late promises cannot paint results into a newly selected project.
Use a monotonically increasing selection token before applying stats responses.

- [ ] **Step 6: Run both focused suites**

```powershell
npm.cmd test -- --run src/components/__tests__/ProjectHistoryList.spec.ts src/views/__tests__/ProjectView.spec.ts
```

Expected: all focused tests pass.

### Task 6: Add explicit drag reorder mode

**Files:**
- Create: `frontend/src/components/ProjectReorderList.vue`
- Create: `frontend/src/components/__tests__/ProjectReorderList.spec.ts`
- Modify: `frontend/src/views/ProjectView.vue`
- Modify: `frontend/src/views/__tests__/ProjectView.spec.ts`

- [ ] **Step 1: Write failing reorder component tests**

Use synthetic HTML5 drag events to prove:

- entering receives a copied manual-order list;
- dragging one item over another changes the draft only;
- cancel emits no order and restores server state;
- save emits every ID exactly once;
- controls are disabled while saving.

- [ ] **Step 2: Run and verify RED**

```powershell
npm.cmd test -- --run src/components/__tests__/ProjectReorderList.spec.ts
```

- [ ] **Step 3: Implement with native drag events**

Use `draggable="true"` and `dragstart`, `dragover.prevent`, and `drop`. Do not
add a drag-and-drop dependency for this single vertical list. Display a visible
drag handle and save/cancel actions.

- [ ] **Step 4: Integrate save, cancel, and conflict recovery**

On save, call `reorderProjects(draftIds)`. Replace `projects` only with the
server response. On `PROJECT_ORDER_CONFLICT`, exit reorder mode, reload the
collection, preserve the selected ID when it still exists, and show an
instruction to retry.

- [ ] **Step 5: Run reorder and ProjectView tests**

Expected: all focused tests pass.

### Task 7: Add the typed deletion confirmation flow

**Files:**
- Create: `frontend/src/components/ProjectDeleteDialog.vue`
- Create: `frontend/src/components/__tests__/ProjectDeleteDialog.spec.ts`
- Modify: `frontend/src/views/ProjectView.vue`
- Modify: `frontend/src/views/__tests__/ProjectView.spec.ts`

- [ ] **Step 1: Write failing dialog tests**

Assert that the dialog:

- lists database and vector-index consequences;
- requires an exact, case-sensitive project-name match;
- keeps delete disabled for whitespace, partial, or wrong-case values;
- emits confirm only when valid;
- closes on cancel when idle;
- remains visible and disabled appropriately while deleting.

- [ ] **Step 2: Run and verify RED**

```powershell
npm.cmd test -- --run src/components/__tests__/ProjectDeleteDialog.spec.ts
```

- [ ] **Step 3: Implement an accessible modal**

Use `role="dialog"`, `aria-modal="true"`, an explicit title, native input and
buttons, and a backdrop. Reset typed text whenever the target project changes or
the dialog closes.

- [ ] **Step 4: Integrate deletion**

After `deleteProject(id)` succeeds:

- remove the item from local state;
- select the next item at the deleted index, otherwise the previous item;
- clear selection if the collection is empty;
- reset details and close the dialog.

On failure, keep the dialog open, preserve the project, and show a sanitized
error. Add ProjectView tests for all branches.

- [ ] **Step 5: Run dialog and page tests**

Expected: all focused tests pass.

### Task 8: Add project-aware shortcuts and target-page prefill

**Files:**
- Create: `frontend/src/utils/projectRoute.ts`
- Create: `frontend/src/utils/__tests__/projectRoute.spec.ts`
- Modify: `frontend/src/views/ProjectView.vue`
- Modify: `frontend/src/views/SearchView.vue`
- Modify: `frontend/src/views/GraphView.vue`
- Modify: `frontend/src/views/AgentChat.vue`
- Modify: `frontend/src/views/__tests__/ProjectView.spec.ts`
- Modify: `frontend/src/views/__tests__/SearchView.spec.ts`
- Modify: `frontend/src/views/__tests__/GraphView.spec.ts`
- Modify: `frontend/src/views/__tests__/AgentChat.spec.ts`

- [ ] **Step 1: Write failing parser tests**

Define one shared parser:

```typescript
export function projectIdFromQuery(value: unknown, fallback = 1): number
```

Tests accept `"7"` and reject missing, arrays, `"7x"`, `"0"`, `"-2"`, decimal,
and unsafe integers.

- [ ] **Step 2: Run parser tests and verify RED**

- [ ] **Step 3: Implement the minimal parser**

Require a string matching `/^[1-9]\d*$/`, convert with `Number`, and require
`Number.isSafeInteger`.

- [ ] **Step 4: Write failing route-prefill tests**

Mount each target view with a memory router at
`?project_id=7`, assert its input starts at `7`, then assert malformed input
falls back to `1`.

- [ ] **Step 5: Initialize each target view from `useRoute().query.project_id`**

Do not watch later query changes and do not alter target layouts. Add
Projects-page `RouterLink` shortcuts to `/search`, `/graph`, and `/chat` with
the selected ID.

- [ ] **Step 6: Run all affected frontend suites**

```powershell
npm.cmd test -- --run src/utils/__tests__/projectRoute.spec.ts src/views/__tests__/ProjectView.spec.ts src/views/__tests__/SearchView.spec.ts src/views/__tests__/GraphView.spec.ts src/views/__tests__/AgentChat.spec.ts
```

### Task 9: Documentation, complete verification, and manual handoff

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/superpowers/plans/2026-07-06-project-history-management.md`

- [ ] **Step 1: Update documentation**

Document the history workspace, API routes, `sort_order` compatibility upgrade,
Qdrant deletion ordering, query-prefill URLs, and the fact that deletion is
irreversible.

- [ ] **Step 2: Run complete backend verification**

```powershell
cd backend
.\.venv\python.exe -m pytest
.\.venv\python.exe -m compileall app scripts
```

Expected: all tests pass, with only explicitly documented existing skips.

- [ ] **Step 3: Run complete frontend verification**

```powershell
cd frontend
npm.cmd test -- --run
npm.cmd run build
```

Expected: all tests pass and the production build succeeds. The existing
Cytoscape bundle-size warning is acceptable; new errors are not.

- [ ] **Step 4: Run repository hygiene checks**

```powershell
git diff --check
git status --short
```

Confirm `.env`, SQLite databases, Qdrant storage, build output, and credentials
are not staged or newly tracked.

- [ ] **Step 5: Produce the user manual test checklist**

Provide ordered scenarios for:

1. empty and populated history;
2. registration and duplicate-path recovery;
3. selection and statistics isolation;
4. filtering, temporary sorting, page sizes, and pagination;
5. drag reorder save/cancel and persistence after refresh;
6. available/unavailable path refresh;
7. scan and vector-index actions;
8. shortcuts and target-page project-ID prefill;
9. typed deletion cancellation, wrong-name blocking, successful cascade, and
   post-delete selection;
10. restart persistence and responsive narrow-screen behavior.

Flag that vector-index construction makes real Embedding calls and should only
be exercised manually by the user. Do not commit or push until the user reports
manual-test results and explicitly authorizes the repository operation.
