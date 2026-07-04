# ResearchCode-Agent Backend

The Week 1 backend registers local source-code projects, scans supported files,
extracts code entities, builds API relationships, and persists a replaceable
project index in SQLite.

## Requirements

- Python 3.11
- Windows PowerShell or Command Prompt

## Local setup

Run these commands from the `backend` directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive OpenAPI
documentation is available at `http://127.0.0.1:8000/docs`.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Run the complete suite with coverage:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing -v
```

## Configuration

Settings use the `RCA_` environment-variable prefix and may also be placed in
`backend/.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `RCA_DATABASE_URL` | `sqlite+pysqlite:///./research_code_agent.db` | SQLAlchemy database URL |
| `RCA_MAX_SOURCE_BYTES` | `2097152` | Maximum source-file size accepted by the scanner |

Example `.env`:

```dotenv
RCA_DATABASE_URL=sqlite+pysqlite:///./research_code_agent.db
RCA_MAX_SOURCE_BYTES=2097152
```

## API verification

Create a project with an absolute path:

```cmd
curl.exe -i -X POST http://127.0.0.1:8000/api/projects -H "Content-Type: application/json" -d "{\"name\":\"Sample\",\"root_path\":\"F:/absolute/path/to/sample_project\"}"
```

Use the returned project ID to scan and read statistics:

```cmd
curl.exe -i -X POST http://127.0.0.1:8000/api/projects/1/scan
curl.exe -i http://127.0.0.1:8000/api/projects/1/stats
```

The scan is a project-level atomic replacement: a successful rescan replaces
the previous files, entities, relations, and issues. If persistence fails, the
previous successful index is preserved.
