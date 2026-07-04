# Week 2 Retrieval and Basic RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic code chunks, local/API embeddings, Qdrant vector indexing, SQLite keyword search, weighted hybrid retrieval, bounded RAG context, and a cited basic code-question-answering API.

**Architecture:** `CodeEntity` remains the durable source of truth. Chunks are derived deterministically at index time, embedded through a provider-neutral interface, and stored in a project-specific Qdrant collection; keyword search reads SQLite directly. Both retrieval paths return one `SearchHit` contract, which feeds hybrid ranking, context construction, and an injectable OpenAI-compatible LLM client.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Pydantic 2, sentence-transformers, OpenAI Python SDK, qdrant-client, SQLite, pytest, pytest-cov.

---

## Scope and execution rules

- Week 2 implements Day 8 through Day 14 from `plan.md`.
- Continue TDD: test first, observe the expected failure, implement minimally, rerun focused and regression tests.
- External network access is never required by automated tests.
- Sentence Transformer model loading is lazy; unit tests inject a fake model.
- Qdrant wrapper tests use `QdrantClient(":memory:")`; no Docker service is required for tests.
- LLM and embedding API tests inject fake SDK clients and never use real credentials.
- Do not persist a second copy of chunk text in SQLite. Rebuilding an index derives chunks from current `code_entities`.
- Collection naming is exactly `project_{project_id}_code_chunks`.
- Search results are always project-scoped and returned in deterministic score/order form.
- Keep synchronous services because the Week 1 API and database layer are synchronous.

## File map

| Path | Responsibility |
| --- | --- |
| `backend/app/retrieval/types.py` | `CodeChunk` and `SearchHit` immutable contracts |
| `backend/app/retrieval/chunk_builder.py` | Convert persisted `CodeEntity` rows to bounded searchable chunks |
| `backend/app/retrieval/embedding_service.py` | Provider-neutral embedding API plus local and OpenAI-compatible providers |
| `backend/app/retrieval/vector_store.py` | Project collection lifecycle, Qdrant upsert, and vector query |
| `backend/app/retrieval/keyword_search.py` | Project-scoped SQLite keyword scoring |
| `backend/app/retrieval/hybrid_search.py` | Deduplicate and combine vector/keyword results |
| `backend/app/rag/context_builder.py` | Convert ranked hits into bounded cited LLM context |
| `backend/app/llm/client.py` | Provider-neutral chat completion and OpenAI-compatible implementation |
| `backend/app/services/vector_index_service.py` | Build/rebuild one project vector index |
| `backend/app/services/code_qa_service.py` | Retrieval → context → LLM orchestration |
| `backend/app/schemas/retrieval.py` | Build-index and search HTTP contracts |
| `backend/app/schemas/agent.py` | Code-QA request/response/reference contracts |
| `backend/app/api/search_api.py` | Build-index, keyword, and hybrid endpoints |
| `backend/app/api/agent_api.py` | Basic code-QA endpoint |
| `backend/app/core/dependencies.py` | Cached production service factories and test override seams |

---

### Task 1: Define retrieval contracts and deterministic code chunks

**Files:**
- Create: `backend/app/retrieval/__init__.py`
- Create: `backend/app/retrieval/types.py`
- Create: `backend/app/retrieval/chunk_builder.py`
- Create: `backend/tests/unit/test_chunk_builder.py`

- [ ] **Step 1: Write the failing chunk tests**

Create ORM-free tests using lightweight objects with the same fields as `CodeEntity`:

```python
from types import SimpleNamespace

from app.retrieval.chunk_builder import CodeChunkBuilder


def entity(**overrides):
    values = {
        "id": 7,
        "entity_key": "backend_api:src/AlertController.java:GET /api/alerts/{id}:4",
        "entity_type": "backend_api",
        "name": "GET /api/alerts/{id}",
        "qualified_name": "GET /api/alerts/{id}",
        "file_path": "src/AlertController.java",
        "start_line": 4,
        "end_line": 8,
        "content": "Alert getAlert(Long id) { return service.find(id); }",
        "metadata_json": '{"http_method":"GET","normalized_path":"/api/alerts/{param}"}',
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_builds_searchable_chunk_with_reference_fields():
    chunk = CodeChunkBuilder(max_content_chars=4000).build(entity())

    assert chunk.entity_id == 7
    assert chunk.file_path == "src/AlertController.java"
    assert chunk.metadata["http_method"] == "GET"
    assert "backend_api" in chunk.searchable_text
    assert "GET /api/alerts/{id}" in chunk.searchable_text
    assert "src/AlertController.java" in chunk.searchable_text


def test_truncates_only_content_and_keeps_identity_text():
    chunk = CodeChunkBuilder(max_content_chars=5).build(
        entity(content="0123456789")
    )

    assert chunk.content == "01234"
    assert chunk.qualified_name == "GET /api/alerts/{id}"
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```cmd
cd /d F:\LIUQINGYUN\ResearchCode_Agent\.worktrees\week2-retrieval-rag\backend
.venv\python.exe -m pytest tests\unit\test_chunk_builder.py -v
```

Expected: import failure for `app.retrieval.chunk_builder`.

- [ ] **Step 3: Implement immutable contracts**

In `types.py` define:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodeChunk:
    chunk_id: str
    entity_id: int
    entity_key: str
    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]
    searchable_text: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    entity_id: int
    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]
    score: float
    source: str
```

- [ ] **Step 4: Implement `CodeChunkBuilder`**

Implement `build(entity)` and `build_many(entities)`. Parse `metadata_json` with `json.loads`, truncate only `content`, and create `searchable_text` in this exact order:

```text
Type: {entity_type}
Name: {name}
Qualified name: {qualified_name}
File: {file_path}
Metadata: {metadata_json sorted by key}
Code:
{truncated content}
```

Set `chunk_id=f"entity:{entity.id}"`. Reject `max_content_chars < 1` with `ValueError`.

- [ ] **Step 5: Verify GREEN and regression**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_chunk_builder.py tests\unit\test_models.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```cmd
git add backend/app/retrieval backend/tests/unit/test_chunk_builder.py
git commit -m "feat: build searchable code chunks"
git push
```

---

### Task 2: Add embedding configuration and provider-neutral service

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/retrieval/embedding_service.py`
- Create: `backend/tests/unit/test_embedding_service.py`

- [ ] **Step 1: Add failing fake-provider tests**

Test the public service rather than model internals:

```python
from app.retrieval.embedding_service import EmbeddingService


class FakeProvider:
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


def test_embedding_service_preserves_batch_order():
    service = EmbeddingService(FakeProvider())
    assert service.embed_documents(["a", "abcd"]) == [[1.0, 1.0], [4.0, 1.0]]


def test_embedding_service_rejects_empty_batches_and_vectors():
    service = EmbeddingService(FakeProvider())
    assert service.embed_documents([]) == []
    assert service.embed_query("abc") == [3.0, 1.0]
```

Also test `LocalSentenceTransformerProvider` with an injected fake model exposing `encode_document` and `encode_query`; assert `normalize_embeddings=True`, `convert_to_numpy=True`, and conversion to `list[list[float]]`.

- [ ] **Step 2: Verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_embedding_service.py -v
```

Expected: import failure.

- [ ] **Step 3: Add dependencies**

Append:

```text
openai
qdrant-client
sentence-transformers
```

Install:

```cmd
.venv\python.exe -m pip install -r requirements.txt
```

- [ ] **Step 4: Extend settings**

Add these defaults to `Settings`:

```python
embedding_provider: str = "local"
embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
embedding_api_key: str | None = None
embedding_base_url: str | None = None
qdrant_url: str | None = None
qdrant_api_key: str | None = None
qdrant_path: str = "./qdrant_storage"
search_default_limit: int = 10
search_max_limit: int = 50
chunk_max_content_chars: int = 4000
```

- [ ] **Step 5: Implement providers**

Define an `EmbeddingProvider` protocol with `embed_documents(texts)` and `embed_query(text)`.

`LocalSentenceTransformerProvider`:

- lazy-imports `SentenceTransformer`;
- lazy-loads the configured model once;
- calls `encode_document` for chunks and `encode_query` for queries;
- passes `normalize_embeddings=True` and `convert_to_numpy=True`;
- converts NumPy arrays to Python float lists.

`OpenAICompatibleEmbeddingProvider`:

```python
client = OpenAI(api_key=api_key, base_url=base_url)
response = client.embeddings.create(model=model, input=texts)
vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
```

Reject missing API keys for the API provider with `ValueError("RCA_EMBEDDING_API_KEY is required")`.

- [ ] **Step 6: Verify GREEN**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_embedding_service.py -v
```

Expected: all tests pass without loading or downloading a real model.

- [ ] **Step 7: Commit**

```cmd
git add backend/requirements.txt backend/app/core/config.py backend/app/retrieval/embedding_service.py backend/tests/unit/test_embedding_service.py
git commit -m "feat: add configurable embedding service"
git push
```

---

### Task 3: Implement the Qdrant vector store

**Files:**
- Create: `backend/app/retrieval/vector_store.py`
- Create: `backend/tests/integration/test_vector_store.py`

- [ ] **Step 1: Write failing in-memory Qdrant tests**

Use a real `QdrantClient(":memory:")` and two `CodeChunk` objects:

```python
def test_rebuild_and_search_project_collection():
    client = QdrantClient(":memory:")
    store = QdrantVectorStore(client)
    store.rebuild(
        project_id=3,
        chunks=[alert_chunk, device_chunk],
        vectors=[[1.0, 0.0], [0.0, 1.0]],
    )

    hits = store.search(project_id=3, query_vector=[0.9, 0.1], limit=1)

    assert hits[0].entity_id == alert_chunk.entity_id
    assert hits[0].source == "vector"
```

Add tests that:

- rebuilding replaces old points;
- project 3 and project 4 use separate collections;
- a chunk/vector length mismatch raises `ValueError`;
- searching a missing project collection returns `[]`.

- [ ] **Step 2: Verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_vector_store.py -v
```

Expected: import failure.

- [ ] **Step 3: Implement Qdrant storage**

Use:

```python
collection_name = f"project_{project_id}_code_chunks"
```

For rebuild:

1. Validate equal non-zero chunk/vector lengths and one common vector dimension.
2. Delete an existing collection.
3. Create it with `VectorParams(size=dimension, distance=Distance.COSINE)`.
4. Upsert `PointStruct` objects.

Create deterministic point IDs with:

```python
str(uuid.uuid5(uuid.NAMESPACE_URL, f"research-code-agent:{project_id}:{chunk.chunk_id}"))
```

Payload must include every `SearchHit` field except `score/source`, plus `entity_key`.

Search with the current Qdrant API:

```python
response = client.query_points(
    collection_name=collection_name,
    query=query_vector,
    with_payload=True,
    limit=limit,
)
```

Convert `response.points` to `SearchHit(source="vector")`.

- [ ] **Step 4: Verify GREEN**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_vector_store.py -v
```

Expected: all tests pass using only memory.

- [ ] **Step 5: Commit**

```cmd
git add backend/app/retrieval/vector_store.py backend/tests/integration/test_vector_store.py
git commit -m "feat: add Qdrant vector store"
git push
```

---

### Task 4: Build project vector indexes and expose the endpoint

**Files:**
- Create: `backend/app/services/vector_index_service.py`
- Create: `backend/app/core/dependencies.py`
- Create: `backend/app/schemas/retrieval.py`
- Create: `backend/app/api/search_api.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_vector_index_api.py`

- [ ] **Step 1: Write failing service and endpoint tests**

The service test uses real SQLite rows plus fake embedding/vector services:

```python
summary = VectorIndexService(
    session,
    chunk_builder=CodeChunkBuilder(),
    embeddings=fake_embeddings,
    vector_store=fake_store,
).build(project_id)

assert summary.project_id == project_id
assert summary.chunks_indexed == entity_count
assert fake_store.project_id == project_id
```

Endpoint contract:

```python
response = client.post(f"/api/projects/{project_id}/build-vector-index")
assert response.status_code == 200
assert response.json() == {
    "project_id": project_id,
    "collection_name": f"project_{project_id}_code_chunks",
    "chunks_indexed": entity_count,
}
```

Assert missing project returns `404 PROJECT_NOT_FOUND`; a project with no entities returns `409 PROJECT_NOT_SCANNED`.

- [ ] **Step 2: Verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_vector_index_api.py -v
```

Expected: route/import failure.

- [ ] **Step 3: Define schemas**

In `retrieval.py`:

```python
class VectorIndexSummary(BaseModel):
    project_id: int
    collection_name: str
    chunks_indexed: int


class SearchRequest(BaseModel):
    project_id: int
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class SearchHitRead(BaseModel):
    entity_id: int
    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]
    score: float
    source: str
```

- [ ] **Step 4: Implement `VectorIndexService`**

Load the project and all `CodeEntity` rows ordered by ID. Raise stable `DomainError` codes for missing/unscanned projects. Build chunks, embed `searchable_text` in batches, and call `vector_store.rebuild`.

- [ ] **Step 5: Add dependency seams and route**

`core/dependencies.py` must expose cached production factories:

```python
get_embedding_service()
get_vector_store()
get_chunk_builder()
```

The route uses FastAPI `Depends`, allowing integration tests to override each factory:

```python
@router.post(
    "/projects/{project_id}/build-vector-index",
    response_model=VectorIndexSummary,
)
def build_vector_index(
    project_id: int,
    session: Session = Depends(get_session),
    chunk_builder: CodeChunkBuilder = Depends(get_chunk_builder),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
) -> VectorIndexSummary:
    return VectorIndexService(
        session,
        chunk_builder=chunk_builder,
        embeddings=embeddings,
        vector_store=vector_store,
    ).build(project_id)
```

Mount `search_router` under `/api`.

- [ ] **Step 6: Verify GREEN and all API tests**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_vector_index_api.py tests\integration\test_scan_api.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```cmd
git add backend/app/core/dependencies.py backend/app/services/vector_index_service.py backend/app/schemas/retrieval.py backend/app/api backend/app/main.py backend/tests/integration/test_vector_index_api.py
git commit -m "feat: expose vector index building"
git push
```

---

### Task 5: Implement project-scoped keyword search

**Files:**
- Create: `backend/app/retrieval/keyword_search.py`
- Modify: `backend/app/api/search_api.py`
- Create: `backend/tests/integration/test_keyword_search.py`

- [ ] **Step 1: Write failing ranking tests**

Persist entities that match the query in different fields and assert ordering:

1. exact case-insensitive `name` match;
2. `qualified_name` contains;
3. API path in `metadata_json` or name;
4. `file_path` contains;
5. `content` contains.

Also assert:

- results never cross `project_id`;
- blank queries are rejected by the HTTP schema;
- results are ordered by score descending, then entity ID ascending;
- `limit` is honored.

- [ ] **Step 2: Verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_keyword_search.py -v
```

Expected: import/route failure.

- [ ] **Step 3: Implement deterministic SQLite scoring**

Select only rows where at least one searchable field contains the escaped query. Calculate score in Python:

```text
1.00 exact name
0.90 qualified_name contains
0.85 API path/name contains when query starts with "/"
0.75 name contains
0.60 file_path contains
0.40 content contains
```

Use the maximum applicable score per entity, not the sum. Return `SearchHit(source="keyword")`.

- [ ] **Step 4: Add endpoint**

```python
@router.post("/search/keyword", response_model=list[SearchHitRead])
def keyword_search(data: SearchRequest, session: Session = Depends(get_session)):
    return KeywordSearchService(session).search(
        data.project_id,
        data.query,
        data.limit,
    )
```

Missing projects return `404 PROJECT_NOT_FOUND`.

- [ ] **Step 5: Verify GREEN**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_keyword_search.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```cmd
git add backend/app/retrieval/keyword_search.py backend/app/api/search_api.py backend/tests/integration/test_keyword_search.py
git commit -m "feat: add keyword code search"
git push
```

---

### Task 6: Implement vector and weighted hybrid search

**Files:**
- Create: `backend/app/retrieval/hybrid_search.py`
- Modify: `backend/app/api/search_api.py`
- Modify: `backend/app/core/dependencies.py`
- Create: `backend/tests/unit/test_hybrid_search.py`
- Create: `backend/tests/integration/test_hybrid_search_api.py`

- [ ] **Step 1: Write failing fusion tests**

Use fake vector and keyword search functions. Cover:

```python
vector_hits = [
    hit(entity_id=1, score=0.9, source="vector"),
    hit(entity_id=2, score=0.6, source="vector"),
]
keyword_hits = [
    hit(entity_id=2, score=1.0, source="keyword"),
    hit(entity_id=3, score=0.8, source="keyword"),
]
```

Assert:

- entity 2 appears once;
- vector scores are divided by the maximum positive vector score;
- keyword scores are divided by the maximum positive keyword score;
- final score is `0.7 * normalized_vector + 0.3 * normalized_keyword`;
- tie-breaking uses entity ID ascending;
- output source is `"hybrid"`;
- empty result lists are supported.

- [ ] **Step 2: Verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_hybrid_search.py -v
```

Expected: import failure.

- [ ] **Step 3: Implement vector search orchestration**

`HybridSearchService.search(project_id, query, limit)`:

1. embed the query once;
2. request `limit * 2` vector hits;
3. request `limit * 2` keyword hits;
4. normalize and merge by `entity_id`;
5. return the first `limit`.

If the vector collection is missing, propagate `DomainError(code="VECTOR_INDEX_NOT_FOUND", status_code=409)` rather than silently returning keyword-only results.

- [ ] **Step 4: Add `/api/search/hybrid`**

Use `SearchRequest` and return `list[SearchHitRead]`. Obtain embeddings/vector store through overridable dependencies.

- [ ] **Step 5: Verify GREEN**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_hybrid_search.py tests\integration\test_hybrid_search_api.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```cmd
git add backend/app/retrieval/hybrid_search.py backend/app/api/search_api.py backend/app/core/dependencies.py backend/tests/unit/test_hybrid_search.py backend/tests/integration/test_hybrid_search_api.py
git commit -m "feat: add weighted hybrid retrieval"
git push
```

---

### Task 7: Build bounded RAG context with citations

**Files:**
- Create: `backend/app/rag/__init__.py`
- Create: `backend/app/rag/context_builder.py`
- Create: `backend/tests/unit/test_rag_context_builder.py`

- [ ] **Step 1: Write failing context tests**

Assert the builder:

- preserves ranked hit order;
- emits `[1]`, `[2]` citation labels;
- includes file path, line range, entity type, qualified name, and content;
- returns structured references separately;
- never exceeds `max_context_chars`;
- skips a hit if even its header cannot fit;
- does not split a citation header.

Example expected block:

```text
[1] src/AlertController.java:4-8
Type: java_method
Name: AlertController.getAlert
Code:
Alert getAlert(Long id) { return alertService.findById(id); }
```

- [ ] **Step 2: Verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_rag_context_builder.py -v
```

Expected: import failure.

- [ ] **Step 3: Implement result contracts and builder**

Define:

```python
@dataclass(frozen=True, slots=True)
class ContextReference:
    citation: int
    entity_id: int
    file_path: str
    start_line: int
    end_line: int
    entity_type: str
    qualified_name: str


@dataclass(frozen=True, slots=True)
class RagContext:
    text: str
    references: Sequence[ContextReference]
```

`RagContextBuilder(max_context_chars=12000).build(hits)` adds complete blocks until the next block would exceed the limit.

- [ ] **Step 4: Verify GREEN**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_rag_context_builder.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```cmd
git add backend/app/rag backend/tests/unit/test_rag_context_builder.py
git commit -m "feat: build cited RAG context"
git push
```

---

### Task 8: Implement OpenAI-compatible LLM and basic code QA

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/dependencies.py`
- Create: `backend/app/llm/__init__.py`
- Create: `backend/app/llm/client.py`
- Create: `backend/app/services/code_qa_service.py`
- Create: `backend/app/schemas/agent.py`
- Create: `backend/app/api/agent_api.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/unit/test_code_qa_service.py`
- Create: `backend/tests/integration/test_code_qa_api.py`

- [ ] **Step 1: Write failing orchestration tests**

Inject fake hybrid search and fake LLM:

```python
response = CodeQaService(
    search=fake_search,
    context_builder=RagContextBuilder(),
    llm=fake_llm,
).answer(project_id=1, question="Where is the alert API implemented?", limit=5)

assert fake_search.query == "Where is the alert API implemented?"
assert "[1]" in fake_llm.user_prompt
assert response.answer == "It is implemented in AlertController [1]."
assert response.references[0].file_path.endswith("AlertController.java")
```

Cover no retrieval hits: return a deterministic answer saying no supporting code was found and do not call the LLM.

- [ ] **Step 2: Verify RED**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_code_qa_service.py -v
```

Expected: import failure.

- [ ] **Step 3: Add LLM settings and client**

Add:

```python
llm_api_key: str | None = None
llm_base_url: str | None = None
llm_model: str = "gpt-4.1-mini"
rag_max_context_chars: int = 12000
```

Define an `LlmClient` protocol:

```python
class LlmClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError
```

Implement using:

```python
client = OpenAI(api_key=api_key, base_url=base_url)
completion = client.chat.completions.create(
    model=model,
    temperature=0,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
)
```

Reject missing `RCA_LLM_API_KEY` when constructing the production client.

- [ ] **Step 4: Implement answer contracts and prompt**

`CodeQaRequest` fields: `project_id`, nonblank `question`, and `limit` from 1 to 20.

`CodeQaResponse` fields: `answer` and `references`.

System prompt requirements:

```text
Answer only from the supplied code context.
Cite claims with [n].
Do not invent files, symbols, APIs, or behavior.
If context is insufficient, say what cannot be determined.
```

- [ ] **Step 5: Add `/api/agent/code-qa`**

The endpoint must resolve `CodeQaService` through an overridable FastAPI dependency so integration tests never use a real LLM.

- [ ] **Step 6: Verify GREEN**

Run:

```cmd
.venv\python.exe -m pytest tests\unit\test_code_qa_service.py tests\integration\test_code_qa_api.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```cmd
git add backend/app/core backend/app/llm backend/app/rag backend/app/services/code_qa_service.py backend/app/schemas/agent.py backend/app/api backend/app/main.py backend/tests/unit/test_code_qa_service.py backend/tests/integration/test_code_qa_api.py
git commit -m "feat: answer cited code questions"
git push
```

---

### Task 9: Complete Week 2 acceptance, documentation, and verification

**Files:**
- Create: `backend/tests/integration/test_week2_acceptance.py`
- Modify: `backend/README.md`
- Create: `backend/.env.example`

- [ ] **Step 1: Write the end-to-end acceptance test**

The test must:

1. register `tests/fixtures/sample_project`;
2. scan it;
3. build its vector index using deterministic fake embeddings and in-memory Qdrant;
4. search keyword `"AlertController"`;
5. hybrid-search `"where is alert lookup implemented"`;
6. call code QA with a fake LLM;
7. assert the final answer has at least one reference with a real file and line range.

Required assertions:

```python
assert build.json()["chunks_indexed"] == 13
assert any(hit["entity_type"] == "java_class" for hit in keyword.json())
assert hybrid.json()[0]["file_path"].endswith("AlertController.java")
assert qa.json()["references"]
assert "[1]" in qa.json()["answer"]
```

- [ ] **Step 2: Run acceptance test**

Run:

```cmd
.venv\python.exe -m pytest tests\integration\test_week2_acceptance.py -v
```

Expected: PASS without network, Docker, or credentials.

- [ ] **Step 3: Document configuration**

Add all new `RCA_` settings to `.env.example` and `backend/README.md`. Document two supported modes:

```text
Local embeddings: sentence-transformers + local Qdrant path
API embeddings: OpenAI-compatible base URL/key/model + Qdrant URL
```

Document that the first local embedding run downloads the configured model and may be slow.

Document these manual commands:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/projects/1/build-vector-index
curl.exe -X POST http://127.0.0.1:8000/api/search/keyword -H "Content-Type: application/json" -d "{\"project_id\":1,\"query\":\"AlertController\",\"limit\":5}"
curl.exe -X POST http://127.0.0.1:8000/api/search/hybrid -H "Content-Type: application/json" -d "{\"project_id\":1,\"query\":\"where is alert lookup implemented\",\"limit\":5}"
curl.exe -X POST http://127.0.0.1:8000/api/agent/code-qa -H "Content-Type: application/json" -d "{\"project_id\":1,\"question\":\"Where is the alert API implemented?\",\"limit\":5}"
```

- [ ] **Step 4: Run complete verification**

Run:

```cmd
.venv\python.exe -m pytest --cov=app --cov-report=term-missing -v
.venv\python.exe -m compileall -q app tests
git diff --check
git status --short
```

Expected:

- all tests pass;
- branch coverage remains at least 80%;
- compileall and diff check exit 0;
- only intended Week 2 files are listed.

- [ ] **Step 5: Run a real local smoke test**

With user approval for model download:

1. start the API;
2. build an index for the sample project using local embeddings and local Qdrant;
3. run keyword and hybrid searches;
4. configure an OpenAI-compatible test endpoint;
5. ask one cited code question.

Stop before committing so the user can inspect the HTTP responses.

- [ ] **Step 6: Commit after user acceptance**

```cmd
git add backend
git commit -m "test: verify week 2 retrieval and RAG flow"
git push
```

---

## Plan self-review

### Main-plan coverage

| `plan.md` Week 2 requirement | Covered by |
| --- | --- |
| Day 8 CodeChunkBuilder and searchable text | Task 1 |
| Day 9 local and API embedding providers | Task 2 |
| Day 10 Qdrant collection/upsert/search and build endpoint | Tasks 3-4 |
| Day 11 SQLite keyword search and API-path priority | Task 5 |
| Day 12 weighted 0.7/0.3 hybrid retrieval | Task 6 |
| Day 13 cited, length-bounded RAG context | Task 7 |
| Day 14 OpenAI-compatible LLM, code QA, references | Task 8 |
| Stable end-to-end Week 2 acceptance | Task 9 |

### Boundary consistency

- `CodeChunk.entity_id` and `SearchHit.entity_id` always refer to `CodeEntity.id`.
- Every retrieval result carries the Week 1 reference fields: file path, start/end lines, type, name, content, metadata.
- `project_id` scopes every database query and every Qdrant collection.
- The same embedding service produces document and query vectors.
- `HybridSearchService` is the only place that applies the required 0.7/0.3 fusion.
- `RagContextBuilder` is the only place that assigns citation numbers.
- `CodeQaService` never invents references; it returns the context builder's references.

### Explicitly deferred

- FTS5 optimization; Week 2 starts with deterministic SQL `LIKE` scoring.
- Reranking/cross-encoders.
- Conversation persistence and unified Agent chat.
- Controller-to-Service call extraction and graph traversal.
- Background vector-index jobs and distributed locking.
- Automatic source-code modification.

### Source/API sanity check

- Sentence Transformers supports `encode_document` and `encode_query` for retrieval-oriented models.
- Current Qdrant Python examples use `query_points`; deprecated `search` is not used.
- Qdrant in-memory mode is used only for tests; persistent local path or server URL is configurable.
- The official OpenAI Python SDK supports both custom `base_url` and embeddings/chat APIs required here.
