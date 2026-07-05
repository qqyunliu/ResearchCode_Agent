# Vector Index Build Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit, retryable vector-index build action to the Projects page with progress feedback and a successful chunk-count summary.

**Architecture:** Extend the existing project API module with a typed wrapper around the current vector-index endpoint. Keep registration, scanning, and indexing in `ProjectView` as three explicit operations controlled by one discriminated operation state, with scan completion gating indexing and a successful rescan invalidating any prior index result.

**Tech Stack:** Vue 3 Composition API, TypeScript, Axios, Vitest, Vue Test Utils, existing FastAPI vector-index endpoint.

---

## File Map

| Path | Responsibility |
| --- | --- |
| `frontend/src/types/project.ts` | Add the backend-compatible vector-index response type. |
| `frontend/src/api/projects.ts` | Add the typed `buildVectorIndex()` API wrapper. |
| `frontend/src/views/ProjectView.vue` | Add operation state, button gating, progress, success, and retryable failure UI. |
| `frontend/src/views/__tests__/ProjectView.spec.ts` | Specify the complete user flow with mocked offline API calls. |

No backend file changes are required. Automated tests must not load an embedding
model, contact Qdrant, or call an external embedding API.

---

### Task 1: Add the typed vector-index API wrapper

**Files:**
- Modify: `frontend/src/types/project.ts`
- Modify: `frontend/src/api/projects.ts`
- Modify: `frontend/src/views/__tests__/ProjectView.spec.ts`

- [ ] **Step 1: Add the API mock and a failing API-call expectation**

Extend the hoisted mock in `ProjectView.spec.ts`:

```typescript
const api = vi.hoisted(() => ({
  buildVectorIndex: vi.fn(),
  createProject: vi.fn(),
  getProjectStats: vi.fn(),
  scanProject: vi.fn(),
}))
```

Add a helper that registers and scans a project using the existing controls:

```typescript
async function registerAndScan(wrapper: VueWrapper) {
  await wrapper.get('[data-test="project-name"]').setValue("Demo")
  await wrapper.get('[data-test="root-path"]').setValue("F:/demo")
  await wrapper.get('[data-test="register-form"]').trigger("submit")
  await flushPromises()
  await wrapper.get('[data-test="scan"]').trigger("click")
  await flushPromises()
}
```

Configure the existing mocks and add the failing behavior test:

```typescript
it("builds the vector index for the scanned project", async () => {
  api.createProject.mockResolvedValue({
    id: 7,
    name: "Demo",
    root_path: "F:/demo",
    status: "created",
  })
  api.scanProject.mockResolvedValue({
    project_id: 7,
    status: "ready",
    files_indexed: 12,
    entities_indexed: 20,
    relations_indexed: 9,
    files_skipped: 1,
    parse_errors: 0,
  })
  api.getProjectStats.mockResolvedValue(stats)
  api.buildVectorIndex.mockResolvedValue({
    project_id: 7,
    collection_name: "project_7_code_chunks",
    chunks_indexed: 31,
  })
  const wrapper = mount(ProjectView)
  await registerAndScan(wrapper)

  await wrapper.get('[data-test="build-index"]').trigger("click")
  await flushPromises()

  expect(api.buildVectorIndex).toHaveBeenCalledWith(7)
})
```

- [ ] **Step 2: Run the focused test and verify RED**

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week4-unified-agent-demo\frontend
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
```

Expected: FAIL because `[data-test="build-index"]` does not exist.

- [ ] **Step 3: Add the response type**

Append to `frontend/src/types/project.ts`:

```typescript
export interface VectorIndexSummary {
  project_id: number
  collection_name: string
  chunks_indexed: number
}
```

- [ ] **Step 4: Add the Axios wrapper**

Import `VectorIndexSummary` in `frontend/src/api/projects.ts`, then add:

```typescript
export async function buildVectorIndex(
  projectId: number,
): Promise<VectorIndexSummary> {
  const response = await axios.post<VectorIndexSummary>(
    `/api/projects/${projectId}/build-vector-index`,
  )
  return response.data
}
```

- [ ] **Step 5: Keep the test RED for the intended UI reason**

Run:

```cmd
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
```

Expected: the build-index test still fails because the UI action is not yet
implemented; existing ProjectView tests remain green.

---

### Task 2: Implement index action state and success output

**Files:**
- Modify: `frontend/src/views/ProjectView.vue`
- Modify: `frontend/src/views/__tests__/ProjectView.spec.ts`

- [ ] **Step 1: Add failing button-gating and success assertions**

Add:

```typescript
it("enables indexing only after a successful scan and shows its result", async () => {
  api.createProject.mockResolvedValue({
    id: 7,
    name: "Demo",
    root_path: "F:/demo",
    status: "created",
  })
  api.scanProject.mockResolvedValue({
    project_id: 7,
    status: "ready",
    files_indexed: 12,
    entities_indexed: 20,
    relations_indexed: 9,
    files_skipped: 1,
    parse_errors: 0,
  })
  api.getProjectStats.mockResolvedValue(stats)
  api.buildVectorIndex.mockResolvedValue({
    project_id: 7,
    collection_name: "project_7_code_chunks",
    chunks_indexed: 31,
  })
  const wrapper = mount(ProjectView)

  expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
    .toBeDefined()
  await registerAndScan(wrapper)
  expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
    .toBeUndefined()

  await wrapper.get('[data-test="build-index"]').trigger("click")
  await flushPromises()

  const result = wrapper.get('[data-test="index-result"]').text()
  expect(result).toContain("31")
  expect(result).toContain("project_7_code_chunks")
})
```

- [ ] **Step 2: Verify the new test fails**

```cmd
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
```

Expected: FAIL because the build button and result do not exist.

- [ ] **Step 3: Replace the boolean loading state**

In `ProjectView.vue`, import `buildVectorIndex` and
`VectorIndexSummary`, then replace:

```typescript
const loading = ref(false)
```

with:

```typescript
type ProjectOperation = "register" | "scan" | "index" | null

const activeOperation = ref<ProjectOperation>(null)
const scanCompleted = ref(false)
const indexSummary = ref<VectorIndexSummary | null>(null)

const busy = computed(() => activeOperation.value !== null)
```

Update `canRegister` to use `!busy.value`.

- [ ] **Step 4: Give registration and scanning explicit state transitions**

Use this registration behavior:

```typescript
async function register() {
  if (!canRegister.value) return
  activeOperation.value = "register"
  errorMessage.value = ""
  try {
    project.value = await createProject({
      name: name.value.trim(),
      root_path: rootPath.value.trim(),
    })
    stats.value = null
    scanCompleted.value = false
    indexSummary.value = null
  } catch {
    errorMessage.value = "Unable to register the project. Check the path and backend."
  } finally {
    activeOperation.value = null
  }
}
```

Use this scan behavior:

```typescript
async function scan() {
  if (!project.value || busy.value) return
  activeOperation.value = "scan"
  errorMessage.value = ""
  indexSummary.value = null
  try {
    await scanProject(project.value.id)
    stats.value = await getProjectStats(project.value.id)
    scanCompleted.value = true
  } catch {
    scanCompleted.value = false
    errorMessage.value = "Unable to scan the project or load its statistics."
  } finally {
    activeOperation.value = null
  }
}
```

- [ ] **Step 5: Implement the index action**

Add:

```typescript
async function buildIndex() {
  if (!project.value || !scanCompleted.value || busy.value) return
  activeOperation.value = "index"
  errorMessage.value = ""
  indexSummary.value = null
  try {
    indexSummary.value = await buildVectorIndex(project.value.id)
  } catch {
    errorMessage.value = (
      "Unable to build the vector index. Confirm the embedding "
      + "configuration and vector store are available."
    )
  } finally {
    activeOperation.value = null
  }
}
```

- [ ] **Step 6: Add the button and result UI**

Place the action beside the scan button:

```vue
<div class="project-actions">
  <button
    data-test="scan"
    :disabled="busy"
    @click="scan"
  >
    {{ activeOperation === "scan" ? "Scanning…" : "Scan and refresh stats" }}
  </button>
  <button
    data-test="build-index"
    :disabled="busy || !scanCompleted"
    @click="buildIndex"
  >
    {{ activeOperation === "index" ? "Building index…" : "Build vector index" }}
  </button>
</div>
```

Render the success result below the project card:

```vue
<article v-if="indexSummary" class="index-result" data-test="index-result">
  <strong>Vector index ready</strong>
  <span>{{ indexSummary.chunks_indexed }} chunks indexed</span>
  <span>Collection: {{ indexSummary.collection_name }}</span>
</article>
```

Change the register label to:

```vue
{{ activeOperation === "register" ? "Registering…" : "Register project" }}
```

- [ ] **Step 7: Run focused tests and verify GREEN**

```cmd
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
```

Expected: all ProjectView tests pass.

---

### Task 3: Cover progress, failure, retry, and reset behavior

**Files:**
- Modify: `frontend/src/views/__tests__/ProjectView.spec.ts`
- Modify: `frontend/src/views/ProjectView.vue`

- [ ] **Step 1: Write a failing progress test**

Add a deferred promise helper:

```typescript
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
```

Then add:

```typescript
it("shows indexing progress and blocks duplicate operations", async () => {
  const pending = deferred<{
    project_id: number
    collection_name: string
    chunks_indexed: number
  }>()
  api.buildVectorIndex.mockReturnValue(pending.promise)
  const wrapper = mount(ProjectView)
  await registerAndScan(wrapper)

  await wrapper.get('[data-test="build-index"]').trigger("click")

  expect(wrapper.get('[data-test="build-index"]').text()).toContain(
    "Building index",
  )
  expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
    .toBeDefined()
  expect(wrapper.get('[data-test="scan"]').attributes("disabled"))
    .toBeDefined()

  pending.resolve({
    project_id: 7,
    collection_name: "project_7_code_chunks",
    chunks_indexed: 31,
  })
  await flushPromises()
})
```

- [ ] **Step 2: Write a failing failure-and-retry test**

Add:

```typescript
it("keeps scan results and permits retry after index failure", async () => {
  api.buildVectorIndex
    .mockRejectedValueOnce(new Error("embedding unavailable"))
    .mockResolvedValueOnce({
      project_id: 7,
      collection_name: "project_7_code_chunks",
      chunks_indexed: 31,
    })
  const wrapper = mount(ProjectView)
  await registerAndScan(wrapper)

  await wrapper.get('[data-test="build-index"]').trigger("click")
  await flushPromises()
  expect(wrapper.get('[data-test="error"]').text()).toContain(
    "Unable to build the vector index",
  )
  expect(wrapper.find('[data-test="stats"]').exists()).toBe(true)
  expect(wrapper.get('[data-test="build-index"]').attributes("disabled"))
    .toBeUndefined()

  await wrapper.get('[data-test="build-index"]').trigger("click")
  await flushPromises()
  expect(api.buildVectorIndex).toHaveBeenCalledTimes(2)
  expect(wrapper.find('[data-test="error"]').exists()).toBe(false)
  expect(wrapper.get('[data-test="index-result"]').text()).toContain("31")
})
```

- [ ] **Step 3: Verify RED**

```cmd
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
```

Expected: at least the progress test fails until every old `loading` binding is
converted to `activeOperation`/`busy`, or the failure test exposes stale result
state.

- [ ] **Step 4: Make the minimum template and style corrections**

Replace every remaining `loading` binding with the corresponding
`activeOperation` or `busy` expression. Add:

```css
.project-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.index-result {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 14px;
  padding: 14px 18px;
  border-radius: 14px;
  background: #ecfdf5;
  color: #166534;
}
```

In the existing mobile media rule, add:

```css
.project-actions {
  align-items: stretch;
  flex-direction: column;
  width: 100%;
}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

```cmd
npm.cmd test -- --run src/views/__tests__/ProjectView.spec.ts
```

Expected: all ProjectView tests pass with no unhandled promise warnings.

---

### Task 4: Full offline verification and manual acceptance gate

**Files:**
- Verify all changed frontend files

- [ ] **Step 1: Run all frontend tests**

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week4-unified-agent-demo\frontend
npm.cmd test -- --run
```

Expected: all frontend test files pass, including Graph and Agent Chat
regressions.

- [ ] **Step 2: Run type checking and production build**

```cmd
npm.cmd run build
```

Expected: `vue-tsc`, Node TypeScript checking, and Vite production build all
succeed. The existing large-chunk warning is non-blocking and outside this
feature's scope.

- [ ] **Step 3: Check the diff and scope**

```cmd
cd ..
git diff --check
git status --short
```

Expected: only the four planned frontend files plus the approved design/plan
documents are changed. `docs/SESSION_HANDOFF.md` remains untracked and excluded.

- [ ] **Step 4: User manual gate**

Ask the user to run the backend and frontend, then verify:

1. register a project;
2. scan and see statistics;
3. confirm `Build vector index` becomes available;
4. click it and observe `Building index…`;
5. confirm `chunks_indexed` and collection name appear;
6. search the same project without a separate `curl.exe` call;
7. if indexing fails, confirm the scan statistics remain and retry is possible.

Warn that this manual action may load/download an embedding model or consume
embedding-provider resources. Stop and wait for approval.

- [ ] **Step 5: Commit and push after approval**

Do not include `docs/SESSION_HANDOFF.md`.

```cmd
git add docs/superpowers/specs/2026-07-05-vector-index-build-action-design.md
git add docs/superpowers/plans/2026-07-05-vector-index-build-action.md
git add frontend/src/types/project.ts
git add frontend/src/api/projects.ts
git add frontend/src/views/ProjectView.vue
git add frontend/src/views/__tests__/ProjectView.spec.ts
git commit -m "feat: add vector index build action"
git push origin codex/week4-unified-agent-demo
```
