# Project History Management Design

## Scope

The Projects page will become a local project-management workspace. It will
list every registered project, let the user select and operate on an existing
project, preserve a user-defined order, detect inaccessible source paths, and
delete a project together with its derived data.

The Search, Graph, and Agent pages remain unchanged except that they may read a
positive `project_id` query parameter supplied by a Projects-page shortcut.

## Chosen architecture

`GET /api/projects` returns the complete project collection. The frontend owns
text filtering, temporary field sorting, and pagination. The backend persists
only the canonical manual order.

This favors simplicity for a local, single-user analysis tool. It avoids a
second unpaginated fetch solely for drag-and-drop ordering. If the product later
needs to manage thousands of projects, server-side filtering and pagination can
replace this contract without changing the visible interaction model.

## Projects-page layout

The registration form remains at the top. Beneath it, the page uses a two-column
workspace:

- The left column contains history controls and the project list.
- The right column contains the selected project's details, actions, statistics,
  shortcuts, index result, and errors.
- Narrow screens stack the columns.

The history controls provide:

- name/path search;
- manual, ID, name, and last-scan sorting;
- page-size selection and pagination;
- manual refresh, which also rechecks path accessibility;
- an explicit reorder mode.

The selected list item is visually distinct. Long paths are truncated visually
but remain available through a title/accessible label.

## Selection and operation rules

- The first project in manual order is selected after the initial load.
- Registering a project inserts it first and selects it.
- Selecting another project clears stale statistics, index results, and errors.
- A selected project whose status is `ready` may build an index without being
  rescanned in the current browser session.
- An inaccessible source path disables scanning, but existing statistics,
  shortcuts, and deletion remain available.
- Refresh and selection do not trigger polling.
- A duplicate-root registration response selects the existing project after
  refreshing the list.

## Manual order

Normal browsing uses pagination. Reorder mode temporarily shows a compact,
unfiltered, unpaginated list in canonical manual order. Search and temporary
field sorting are disabled until the user saves or cancels.

Saving sends the complete ordered project-ID list. The backend accepts it only
when it contains every current project exactly once. A concurrent create/delete
therefore produces a conflict instead of silently losing an item. Cancel
restores the last server-confirmed order.

New projects receive the first position. Existing rows are shifted so order
values remain unique and deterministic.

## Persistence and compatibility

The `projects` table gains a non-null integer `sort_order`. This repository does
not currently use Alembic, and SQLAlchemy `create_all()` cannot add columns to an
existing SQLite table. A focused, idempotent startup migration will:

1. inspect the `projects` table;
2. add `sort_order` when absent;
3. assign deterministic values based on existing `created_at` and `id`;
4. run before normal metadata creation/use.

The migration is intentionally small and SQLite-specific. Introducing Alembic
is deferred until the project needs multiple schema revisions.

## API contracts

`GET /api/projects` returns an array ordered by `sort_order`, then ID. Each item
contains:

- `id`, `name`, `root_path`, `status`;
- `created_at`, `last_scan_at`, `sort_order`;
- `path_accessible`.

`PUT /api/projects/order` accepts:

```json
{"project_ids": [3, 1, 2]}
```

It returns the reordered project array. Duplicate, missing, or unknown IDs
produce `409 PROJECT_ORDER_CONFLICT`.

`DELETE /api/projects/{project_id}` returns `204` after removing both the
project's Qdrant collection and database row. Missing projects return
`404 PROJECT_NOT_FOUND`.

## Deletion consistency and safety

The frontend opens a second-stage confirmation dialog. It names the affected
data and requires the exact project name before enabling deletion.

The backend deletes the Qdrant collection first and then deletes the database
project in a transaction. ORM cascades remove code files, entities, relations,
scan issues, conversations, and messages. If database deletion then fails, the
project remains but its vector index must be rebuilt; this is recoverable and
preferable to an orphaned Qdrant collection.

Deleting a missing collection is successful. A Qdrant failure prevents database
deletion and is exposed as a sanitized `502 VECTOR_STORE_DELETE_FAILED`.

## Shortcuts

The Projects page links to:

- `/search?project_id=<id>`
- `/graph?project_id=<id>`
- `/chat?project_id=<id>`

Each target page accepts only a positive integer. Missing, repeated, malformed,
zero, and negative values fall back to project ID `1`.

## Error and empty states

The UI distinguishes:

- initial loading;
- no registered projects;
- no projects matching the filter;
- list refresh failure;
- statistics failure;
- reorder conflict/failure;
- deletion failure;
- scan/index failure.

Errors stay near the operation that produced them. A failed selection-specific
request must not replace the project list.

## Verification

Backend tests cover schema migration, list ordering and accessibility, reorder
validation, cascade deletion, Qdrant deletion, and failure mapping.

Frontend tests cover loading and empty states, selection, filter/sort/pagination,
 reorder save/cancel, duplicate registration recovery, inaccessible paths,
deletion confirmation, shortcuts, and query-parameter prefill.

No automated test makes a real LLM or Embedding request. Final verification uses
the complete backend suite, complete frontend suite, production build, and a
user-executed manual test checklist.
