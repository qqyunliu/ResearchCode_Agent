# Week 1 Code Ingestion Design

## 1. Purpose

Week 1 builds the reliable code-ingestion foundation for ResearchCode-Agent. A user registers a local research-code repository, starts a scan, and receives persisted file statistics, parsed code entities, and relationships for Java/Spring Boot, Vue/JavaScript/TypeScript, and Python.

This design deliberately excludes vector search, Qdrant, LLM calls, GraphRAG traversal, the Vue management UI, and change planning. Those capabilities depend on the structured data produced here and will be designed separately.

## 2. Success Criteria

The Week 1 milestone is complete when:

1. `GET /health` returns `{"status": "ok"}`.
2. `POST /api/projects` validates and stores a local project.
3. `POST /api/projects/{project_id}/scan` scans supported source files, replaces the project's previous index atomically, and reports skipped or failed files.
4. Java parsing extracts classes, methods, Spring controllers, services, and backend API definitions.
5. Vue/JavaScript/TypeScript parsing extracts supported Axios and request-wrapper API calls.
6. Python parsing extracts classes, synchronous functions, asynchronous functions, arguments, and source ranges.
7. The relation builder creates `CONTAINS`, `DEFINES_API`, and matched `REQUESTS_API` relationships.
8. `GET /api/projects/{project_id}/stats` returns deterministic file, line, language, entity, API, relation, skipped-file, and parse-error counts.
9. Repeating a scan does not create duplicate files, entities, or relations.
10. Unit and integration tests run without access to a real laboratory repository.

## 3. Architecture

The service uses Python 3.11, FastAPI, Pydantic 2, synchronous SQLAlchemy 2, SQLite, tree-sitter, and pytest.

The main data flow is:

```text
Create project
  -> validate and normalize root_path
  -> discover supported files
  -> collect hashes, languages, line counts, and scan issues
  -> parse each readable source file into parser DTOs
  -> build normalized entities and relationships
  -> replace the project's prior index in one database transaction
  -> return scan summary and persisted statistics
```

The API layer validates transport data and translates domain errors to HTTP responses. It does not scan files, parse code, or manage transactions.

Parsers are database-independent. Each parser receives a normalized relative path and decoded source text and returns typed DTOs. `IndexService` assigns persistent identifiers, builds relationships, and owns the replacement transaction.

## 4. Project Structure

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── project_api.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── database.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── project.py
│   │   ├── code_file.py
│   │   ├── code_entity.py
│   │   ├── code_relation.py
│   │   └── scan_issue.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── project.py
│   │   ├── scan.py
│   │   └── stats.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scanner.py
│   │   └── index_service.py
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── java_parser.py
│   │   ├── vue_parser.py
│   │   ├── python_parser.py
│   │   └── relation_builder.py
│   └── utils/
│       ├── __init__.py
│       ├── api_normalizer.py
│       ├── hash_utils.py
│       └── path_utils.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── sample_project/
│   ├── unit/
│   └── integration/
├── pyproject.toml
└── requirements.txt
```

Each file has one responsibility. ORM models define persistence only; Pydantic schemas define API contracts; parser DTOs define the boundary between parsing and indexing.

## 5. Persistence Model

### 5.1 Project

`projects` stores:

- `id`: integer primary key.
- `name`: required display name.
- `root_path`: normalized absolute path, unique.
- `status`: `created`, `scanning`, `ready`, or `failed`.
- `last_scan_at`: nullable UTC timestamp.
- `created_at` and `updated_at`: UTC timestamps.

Registering the same normalized `root_path` twice returns HTTP `409`.

### 5.2 CodeFile

`code_files` stores one row per indexed source file:

- `id`, `project_id`.
- `file_path`: POSIX-style path relative to the project root.
- `language`.
- `line_count`.
- `file_hash`: SHA-256 of raw bytes.
- `size_bytes`.

`(project_id, file_path)` is unique.

### 5.3 CodeEntity

`code_entities` stores:

- `id`, `project_id`, and `file_id`.
- `entity_key`: deterministic key unique within a project.
- `entity_type`.
- `name` and `qualified_name`.
- `file_path`.
- one-based inclusive `start_line` and `end_line`.
- `content`.
- `metadata_json`.

`(project_id, entity_key)` is unique. Entity keys use this form:

```text
{entity_type}:{relative_file_path}:{qualified_name}:{start_line}
```

Week 1 entity types are:

- `java_class`
- `java_method`
- `backend_api`
- `frontend_api_call`
- `python_class`
- `python_function`

### 5.4 CodeRelation

`code_relations` stores:

- `id`, `project_id`.
- `source_id` and `target_id`.
- `relation_type`.
- `confidence`.
- `metadata_json`.

`(project_id, source_id, target_id, relation_type)` is unique.

Week 1 relation types are:

- `CONTAINS`
- `DEFINES_API`
- `REQUESTS_API`

`CALLS_METHOD` is reserved for the Week 3 Controller-to-Service design and is not implemented in Week 1.

### 5.5 ScanIssue

`scan_issues` records non-fatal scan outcomes:

- `id`, `project_id`.
- `file_path`.
- `issue_type`: `skipped` or `parse_error`.
- `reason_code`.
- `message`.

Issues are replaced with the rest of the project index on each scan.

## 6. Scanner Design

The scanner accepts an existing directory after resolving it to an absolute path. It never follows directory symlinks. A symlinked file is skipped to prevent scanning outside the registered root.

Ignored directories are:

```text
.git
node_modules
dist
build
target
__pycache__
.idea
.vscode
.venv
venv
```

Supported extensions are:

| Extension | Language |
| --- | --- |
| `.java` | `java` |
| `.py` | `python` |
| `.vue` | `vue` |
| `.js` | `javascript` |
| `.jsx` | `javascript` |
| `.ts` | `typescript` |
| `.tsx` | `typescript` |
| `.sql` | `sql` |
| `.xml` | `xml` |
| `.yml`, `.yaml` | `yaml` |
| `.json` | `json` |

Only Java, Python, Vue, JavaScript, and TypeScript files are parsed during Week 1. Other supported files contribute to file and line statistics.

Files larger than 2 MiB, files containing a NUL byte in the first 8 KiB, unreadable files, symlinked files, and files that cannot be decoded as UTF-8 or UTF-8 with BOM are skipped with a `ScanIssue`.

Line counts use decoded text and treat an empty file as zero lines.

## 7. Parser Design

### 7.1 Common Contract

Every parser implements:

```python
class SourceParser(Protocol):
    def supports(self, language: str) -> bool: ...
    def parse(self, file_path: str, source: str) -> ParseResult: ...
```

`ParseResult` contains `entities` and parser-local relationship candidates. An `EntityCandidate` includes type, name, qualified name, source range, content, and JSON-compatible metadata.

A syntax error may produce partial entities when tree-sitter can identify complete nodes. An unexpected parser exception becomes a `parse_error` issue for that file and does not abort the project scan.

### 7.2 Java and Spring

tree-sitter extracts class declarations, method declarations, annotations, and source ranges. Annotation text is interpreted with focused helpers.

Supported Spring class annotations:

- `@RestController`
- `@Controller`
- `@Service`
- class-level `@RequestMapping`

Supported method annotations:

- `@RequestMapping`
- `@GetMapping`
- `@PostMapping`
- `@PutMapping`
- `@DeleteMapping`
- `@PatchMapping`

The parser combines class and method paths and emits one `backend_api` per HTTP method and path combination. If `@RequestMapping` omits `method`, metadata uses `ANY`.

Backend API metadata contains:

```json
{
  "http_method": "GET",
  "path": "/api/alerts/{id}",
  "normalized_path": "/api/alerts/{param}",
  "controller_class": "AlertController",
  "handler_method": "getAlert"
}
```

### 7.3 Vue, JavaScript, and TypeScript

For `.vue` files, the parser extracts each `<script>` or `<script setup>` block and preserves its starting line offset. tree-sitter parses JavaScript or TypeScript based on the `lang` attribute.

Week 1 recognizes:

- `axios.get(url)`
- `axios.post(url, data)`
- `axios.put(url, data)`
- `axios.patch(url, data)`
- `axios.delete(url)`
- `request.get(url)`
- `request.post(url, data)`
- `request.put(url, data)`
- `request.patch(url, data)`
- `request.delete(url)`
- `request({ url, method })`

Only string literals and template literals whose dynamic segments can be normalized are indexed. Calls where method or URL cannot be determined become no entity rather than a guessed entity.

### 7.4 Python

The standard `ast` module extracts:

- classes;
- functions;
- async functions;
- positional-only, positional, keyword-only, variadic, and keyword-variadic argument names;
- decorators;
- one-based source ranges and source text.

Methods use a class-qualified name such as `Detector.predict`. Nested functions include their enclosing function names.

Imports may be stored in entity metadata but do not create relations in Week 1.

## 8. API Path Normalization and Relations

Paths are normalized before matching:

1. Remove query strings and fragments.
2. Ensure exactly one leading slash.
3. Collapse repeated slashes.
4. Remove a trailing slash except for `/`.
5. Convert `{id}`, `:id`, `${id}`, and numeric path segments to `{param}`.

`REQUESTS_API` requires equal normalized paths and compatible HTTP methods. `ANY` is compatible with every method. Exact method matches use confidence `1.0`; an `ANY` backend mapping uses `0.8`.

`DEFINES_API` links a backend API entity to its Java handler method. `CONTAINS` links files to top-level entities and classes to their methods.

Unmatched frontend calls and backend APIs remain indexed without a relationship.

## 9. Transaction and Rescan Semantics

Week 1 uses project-level full replacement rather than incremental indexing.

1. Validate and scan files outside the replacement transaction.
2. Parse all readable files and build candidates.
3. Begin a database transaction.
4. Set project status to `scanning`.
5. Delete the project's prior relations, entities, files, and issues.
6. Insert new files, entities, relations, and issues.
7. Set project status to `ready`, update `last_scan_at`, and commit.

If persistence fails, the transaction rolls back and preserves the previous successful index. The service then sets the project status to `failed` in a separate short transaction.

Concurrent scans for the same project are rejected with HTTP `409`. Week 1 enforces this with an in-process project lock because the application is single-process. Multi-process locking is outside this milestone.

## 10. HTTP Contracts

### 10.1 Create Project

`POST /api/projects`

Request:

```json
{
  "name": "Laboratory Alert Platform",
  "root_path": "F:\\research\\alert-platform"
}
```

Response `201`:

```json
{
  "id": 1,
  "name": "Laboratory Alert Platform",
  "root_path": "F:\\research\\alert-platform",
  "status": "created"
}
```

### 10.2 Scan Project

`POST /api/projects/{project_id}/scan`

Response `200`:

```json
{
  "project_id": 1,
  "status": "ready",
  "files_indexed": 42,
  "entities_indexed": 136,
  "relations_indexed": 58,
  "files_skipped": 2,
  "parse_errors": 1
}
```

### 10.3 Project Statistics

`GET /api/projects/{project_id}/stats`

Response `200` includes:

- total files and lines;
- counts grouped by language;
- counts grouped by entity type;
- backend API count;
- frontend API call count;
- relation count grouped by relation type;
- skipped-file count;
- parse-error count;
- last scan timestamp.

## 11. Error Handling

| Condition | Result |
| --- | --- |
| Root path does not exist or is not a directory | HTTP `422` |
| Root path is already registered | HTTP `409` |
| Project ID does not exist | HTTP `404` |
| Scan for project is already running | HTTP `409` |
| Individual file is unreadable, unsafe, too large, binary, or undecodable | Record `skipped`; continue |
| Parser fails for one file | Record `parse_error`; continue |
| Database replacement fails | Roll back; preserve old index; project becomes `failed`; HTTP `500` |

API errors use a stable body:

```json
{
  "detail": {
    "code": "PROJECT_NOT_FOUND",
    "message": "Project 99 does not exist."
  }
}
```

Logs may include exception traces and absolute paths. HTTP responses must not expose stack traces.

## 12. Testing Strategy

Development follows test-driven tasks. Each behavior is introduced with a failing test, minimal implementation, and passing test before the next behavior.

Unit tests cover:

- path resolution, symlink rejection, ignore rules, encoding, binary detection, size limits, hashing, and line counts;
- API path normalization;
- Java classes, methods, mappings, combined paths, and multiple HTTP methods;
- Vue script offsets and supported request forms;
- Python classes, functions, async functions, nested names, and arguments;
- relation construction and confidence values.

Integration tests use a temporary SQLite database and `tests/fixtures/sample_project` to cover:

- health check;
- project creation and duplicate-root rejection;
- first scan;
- repeated scan without duplicates;
- stale-row removal after fixture changes copied to a temporary directory;
- scan summary and statistics;
- non-fatal skipped files and parse errors;
- rollback preserving a previous successful index.

The sample project contains a small Spring controller and service, a Vue page and request wrapper, and a Python algorithm module. It contains no network dependency.

## 13. Operational Constraints

- The Week 1 service runs locally and may access only paths explicitly registered by the user.
- SQLite is sufficient for the single-user, single-process demonstration.
- Database tables are created on application startup for Week 1. Schema migrations are introduced before a deployed or multi-user release.
- The maximum source-file size defaults to 2 MiB and is configurable.
- Scan behavior is deterministic for a fixed directory tree and file content.

## 14. Deferred Work

The following are explicitly deferred:

- incremental indexing using `file_hash`;
- Qdrant and embeddings;
- keyword, vector, and hybrid retrieval;
- Controller-to-Service `CALLS_METHOD` inference;
- graph traversal and GraphRAG;
- the Vue management UI;
- background task queues;
- cross-process scan locks;
- user authentication and authorization;
- automatic code modification.

