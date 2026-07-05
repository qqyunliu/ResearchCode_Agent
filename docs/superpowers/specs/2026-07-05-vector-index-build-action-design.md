# Vector Index Build Action Design

**Date:** 2026-07-05
**Status:** Approved approach, pending written-spec review

## Goal

Add an explicit vector-index build action to the existing Projects page so a
user can complete the full preparation flow without switching to `curl.exe`:

```text
register project
-> scan project
-> build vector index
-> use Search, Graph, or Agent Chat
```

The improvement must show progress, report the number of indexed chunks, and
present a useful retryable error when indexing fails.

## Scope

The change is frontend-only and reuses the existing endpoint:

```http
POST /api/projects/{project_id}/build-vector-index
```

Files expected to change:

- `frontend/src/types/project.ts`
- `frontend/src/api/projects.ts`
- `frontend/src/views/ProjectView.vue`
- `frontend/src/views/__tests__/ProjectView.spec.ts`

No backend endpoint, database schema, routing, or Agent behavior changes are
required.

## User Experience

The Projects page keeps registration, scanning, and indexing as three explicit
actions. Indexing does not start automatically after scanning because it may
load an embedding model, contact an embedding provider, or take materially
longer than source scanning.

The `Build vector index` button is disabled until the current page session has
completed a successful scan for the registered project. During indexing its
label changes to `Building index…`, and all conflicting project operations are
disabled.

On success, the project card displays:

- `Vector index ready`;
- the returned `chunks_indexed` count;
- the returned collection name.

On failure, the existing project and scan statistics remain visible. The page
shows:

```text
Unable to build the vector index. Confirm the embedding configuration and
vector store are available.
```

The button becomes available again so the user can retry.

## State Model

Replace the page's single boolean loading flag with:

```typescript
type ProjectOperation = "register" | "scan" | "index" | null
```

The page also stores:

```typescript
scanCompleted: boolean
indexSummary: VectorIndexSummary | null
```

Only one operation may run at a time. Registering a new project clears the
previous scan and index state. A successful rescan clears the previous index
summary because the indexed source may have changed and the old success result
is no longer proof that the current scan is indexed.

## API and Types

Add:

```typescript
interface VectorIndexSummary {
  project_id: number
  collection_name: string
  chunks_indexed: number
}
```

Add the API wrapper:

```typescript
buildVectorIndex(projectId: number): Promise<VectorIndexSummary>
```

It posts to the existing backend endpoint and returns `response.data`.

## Error Handling

Registration, scanning, and indexing retain operation-specific error messages.
An index failure must not clear:

- the registered project;
- scan statistics;
- the fact that scanning succeeded.

It clears any previous index success summary before a new build starts, so a
failed rebuild cannot leave a misleading success result on screen.

## Testing

Development follows TDD. Extend `ProjectView.spec.ts` to prove:

1. the build button is unavailable before a successful scan;
2. a successful scan enables it;
3. clicking it calls `buildVectorIndex` with the current project ID;
4. the in-progress label is visible and duplicate actions are disabled;
5. success displays `chunks_indexed` and `collection_name`;
6. failure displays the index-specific error and permits retry;
7. registering another project resets scan and index state;
8. existing registration, scan, statistics, error, full-suite, type-check, and
   production-build checks continue to pass.

Automated tests mock the API. They must not load or download an embedding model,
contact a vector database, or access external services.

## Manual Acceptance

Using a configured local backend:

1. register a project;
2. scan it and confirm statistics;
3. click `Build vector index`;
4. observe `Building index…`;
5. confirm the chunk count and collection name;
6. open Search and query the same project without running a separate API
   command.

Manual indexing may load the configured embedding model or consume embedding
provider resources. The user controls whether to run that operation.

## Non-goals

- automatic indexing after every scan;
- background job progress or cancellation;
- persistent frontend recovery of index status after a page reload;
- an index-status polling endpoint;
- deleting or partially rebuilding an index;
- changing embedding or Qdrant configuration from the browser.
