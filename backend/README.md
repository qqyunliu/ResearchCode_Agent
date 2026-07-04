# ResearchCode-Agent Backend

The backend registers and scans local source-code projects, extracts code
entities and relationships into SQLite, builds project-scoped vector indexes,
and answers code questions with file-and-line citations.

## Week 2 retrieval flow

```text
CodeEntity rows
  -> CodeChunkBuilder
  -> embedding provider
  -> Qdrant vector index
  -> keyword + vector hybrid search
  -> bounded cited RAG context
  -> OpenAI-compatible LLM
  -> answer + structured references
```

Each Qdrant collection is isolated by project:

```text
project_{project_id}_code_chunks
```

## Requirements

- Python 3.11
- Windows Command Prompt
- Network access for the first local embedding-model download
- An OpenAI-compatible API key only when making real code-QA requests

## Local setup

Run these commands from the `backend` directory:

```cmd
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

When using the existing Conda-prefix environment in this repository, use:

```cmd
.venv\python.exe -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`, and interactive OpenAPI
documentation is at `http://127.0.0.1:8000/docs`.

Never commit `backend/.env`; it is ignored by Git. Keep API keys only in that
local file or in process environment variables.

## Configuration

Settings use the `RCA_` prefix and can be placed in `backend/.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `RCA_DATABASE_URL` | `sqlite+pysqlite:///./research_code_agent.db` | SQLAlchemy database URL |
| `RCA_MAX_SOURCE_BYTES` | `2097152` | Maximum source-file size |
| `RCA_EMBEDDING_PROVIDER` | `local` | `local` or OpenAI-compatible `api` embeddings |
| `RCA_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model name |
| `RCA_EMBEDDING_API_KEY` | empty | API embedding credential |
| `RCA_EMBEDDING_BASE_URL` | empty | API embedding base URL |
| `RCA_QDRANT_URL` | empty | Remote Qdrant URL; empty uses local storage |
| `RCA_QDRANT_API_KEY` | empty | Remote Qdrant credential |
| `RCA_QDRANT_PATH` | `./qdrant_storage` | Local Qdrant directory |
| `RCA_SEARCH_DEFAULT_LIMIT` | `10` | Default retrieval result limit |
| `RCA_SEARCH_MAX_LIMIT` | `50` | Maximum retrieval result limit |
| `RCA_CHUNK_MAX_CONTENT_CHARS` | `4000` | Maximum code content per chunk |
| `RCA_LLM_API_KEY` | empty | OpenAI-compatible chat credential |
| `RCA_LLM_BASE_URL` | empty | OpenAI-compatible chat base URL |
| `RCA_LLM_MODEL` | `gpt-4.1-mini` | Chat model name |
| `RCA_RAG_MAX_CONTEXT_CHARS` | `12000` | Maximum RAG context size |

### Local embeddings and Qdrant

The default mode runs `sentence-transformers` on CPU and stores vectors under
`RCA_QDRANT_PATH`. The first embedding request downloads the configured model
and can take substantially longer than later requests. Subsequent requests use
the local model cache.

```dotenv
RCA_EMBEDDING_PROVIDER=local
RCA_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RCA_QDRANT_PATH=./qdrant_storage
```

### API embeddings and remote Qdrant

For an OpenAI-compatible embedding service and remote Qdrant:

```dotenv
RCA_EMBEDDING_PROVIDER=api
RCA_EMBEDDING_MODEL=your-embedding-model
RCA_EMBEDDING_API_KEY=your-key
RCA_EMBEDDING_BASE_URL=https://provider.example/v1
RCA_QDRANT_URL=https://qdrant.example
RCA_QDRANT_API_KEY=your-qdrant-key
```

The document and query embedding model must be the same and must return vectors
with the same dimension.

### OpenAI-compatible code QA

Configure a compatible chat endpoint:

```dotenv
RCA_LLM_API_KEY=your-key
RCA_LLM_BASE_URL=https://provider.example/v1
RCA_LLM_MODEL=your-chat-model
```

Automated tests always inject a Fake LLM and never consume paid LLM tokens.
Real `/api/agent/code-qa` calls do consume provider tokens.

## Run tests

With the existing Conda-prefix environment:

```cmd
.venv\python.exe -m pytest -v
```

Run the complete suite with coverage:

```cmd
.venv\python.exe -m pytest --cov=app --cov-report=term-missing -v
```

Run only the offline Week 2 acceptance flow:

```cmd
.venv\python.exe -m pytest tests\integration\test_week2_acceptance.py -v
```

The acceptance test uses deterministic fake embeddings, in-memory Qdrant, and
a Fake LLM. It requires no network, Docker, credentials, or paid tokens.

## Manual API flow

Register and scan a project first:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/projects -H "Content-Type: application/json" -d "{\"name\":\"Sample\",\"root_path\":\"F:/absolute/path/to/sample_project\"}"
curl.exe -X POST http://127.0.0.1:8000/api/projects/1/scan
```

Build the vector index:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/projects/1/build-vector-index
```

Search by exact text:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/search/keyword -H "Content-Type: application/json" -d "{\"project_id\":1,\"query\":\"AlertController\",\"limit\":5}"
```

Search by weighted keyword and semantic retrieval:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/search/hybrid -H "Content-Type: application/json" -d "{\"project_id\":1,\"query\":\"where is alert lookup implemented\",\"limit\":5}"
```

Ask a cited code question. This request calls the configured LLM and consumes
provider tokens:

```cmd
curl.exe -X POST http://127.0.0.1:8000/api/agent/code-qa -H "Content-Type: application/json" -d "{\"project_id\":1,\"question\":\"Where is the alert API implemented?\",\"limit\":5}"
```

The response contains the generated `answer` plus structured `references` with
entity IDs, file paths, line ranges, entity types, and qualified names.
