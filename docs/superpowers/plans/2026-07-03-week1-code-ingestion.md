# Week 1 Code Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested FastAPI backend that registers local projects, scans supported files, parses Java/Vue/Python entities, persists relationships atomically, and returns deterministic project statistics.

**Architecture:** API routes delegate to a synchronous service layer. Parsers return database-independent DTOs; `IndexService` owns project-level replacement transactions and relation persistence. SQLite stores projects, files, entities, relations, and scan issues, while tree-sitter and Python `ast` provide structural parsing.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, SQLite, tree-sitter, tree-sitter-language-pack, pytest, HTTPX

**Design reference:** `docs/superpowers/specs/2026-07-03-week1-code-ingestion-design.md`

---

## File Map

Create these production files:

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application and health endpoint
│   ├── api/project_api.py         # Project, scan, and stats HTTP routes
│   ├── core/config.py             # Environment-backed settings
│   ├── core/database.py           # SQLAlchemy engine/session lifecycle
│   ├── errors.py                  # Stable domain exceptions
│   ├── models/
│   │   ├── base.py                # Declarative base and UTC timestamps
│   │   ├── project.py
│   │   ├── code_file.py
│   │   ├── code_entity.py
│   │   ├── code_relation.py
│   │   └── scan_issue.py
│   ├── schemas/
│   │   ├── project.py
│   │   ├── scan.py
│   │   └── stats.py
│   ├── services/
│   │   ├── project_service.py     # Project registration
│   │   ├── scanner.py             # Filesystem discovery and decoding
│   │   └── index_service.py       # Parsing, replacement, and statistics
│   ├── parsers/
│   │   ├── base.py                # Parser DTOs and protocol
│   │   ├── registry.py            # Language-to-parser dispatch
│   │   ├── java_parser.py
│   │   ├── vue_parser.py
│   │   ├── python_parser.py
│   │   └── relation_builder.py
│   └── utils/
│       ├── api_normalizer.py
│       ├── hash_utils.py
│       └── path_utils.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/sample_project/
│   ├── unit/
│   └── integration/
├── pyproject.toml
└── requirements.txt
```

Every Python package directory also receives an empty `__init__.py`.

## Shared Domain Types

Use these names consistently throughout all tasks:

```python
EntityType = Literal[
    "java_class",
    "java_method",
    "backend_api",
    "frontend_api_call",
    "python_class",
    "python_function",
]

RelationType = Literal["CONTAINS", "DEFINES_API", "REQUESTS_API"]

@dataclass(frozen=True, slots=True)
class EntityCandidate:
    local_key: str
    entity_type: EntityType
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata: dict[str, object]

@dataclass(frozen=True, slots=True)
class RelationCandidate:
    source_key: str
    target_key: str
    relation_type: RelationType
    confidence: float
    metadata: dict[str, object]

@dataclass(frozen=True, slots=True)
class ParseResult:
    entities: tuple[EntityCandidate, ...] = ()
    relations: tuple[RelationCandidate, ...] = ()
```

---

### Task 1: Bootstrap the Backend and Health Check

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Add the failing health test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Add dependency and pytest configuration**

```text
# backend/requirements.txt
fastapi
uvicorn
sqlalchemy
pydantic-settings
tree-sitter
tree-sitter-language-pack
httpx
pytest
pytest-cov
```

```toml
# backend/pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"

[tool.coverage.run]
source = ["app"]
branch = true

[tool.coverage.report]
show_missing = true
fail_under = 80
```

- [ ] **Step 3: Create a Python 3.11 virtual environment and install dependencies**

Run:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Expected: installation exits with code `0`.

- [ ] **Step 4: Run the test and verify the missing application failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_health.py -v
```

Expected: collection fails with `ModuleNotFoundError` or `ImportError` for `app.main`.

- [ ] **Step 5: Implement the minimal application**

```python
# backend/app/main.py
from fastapi import FastAPI

app = FastAPI(title="ResearchCode-Agent")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Verify the health test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_health.py -v
```

Expected: `1 passed`.

- [ ] **Step 7: Commit**

```powershell
git add backend
git commit -m "feat: bootstrap FastAPI backend"
```

---

### Task 2: Add Database Configuration and ORM Models

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/project.py`
- Create: `backend/app/models/code_file.py`
- Create: `backend/app/models/code_entity.py`
- Create: `backend/app/models/code_relation.py`
- Create: `backend/app/models/scan_issue.py`
- Create: `backend/tests/unit/test_models.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the failing model test**

```python
# backend/tests/unit/test_models.py
from sqlalchemy import create_engine, inspect

from app.models.base import Base


def test_metadata_contains_all_week1_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "projects",
        "code_files",
        "code_entities",
        "code_relations",
        "scan_issues",
    }
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py -v
```

Expected: import failure for `app.models.base`.

- [ ] **Step 3: Implement configuration and the declarative base**

```python
# backend/app/core/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///./research_code_agent.db"
    max_source_bytes: int = 2 * 1024 * 1024
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RCA_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# backend/app/models/base.py
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
```

```python
# backend/app/core/database.py
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
```

- [ ] **Step 4: Implement the five ORM models**

Use integer foreign keys with `ondelete="CASCADE"`, JSON stored as `Text`, and these exact uniqueness constraints:

```python
# backend/app/models/project.py
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    root_path: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    last_scan_at: Mapped[datetime | None] = mapped_column(nullable=True)

    files = relationship("CodeFile", cascade="all, delete-orphan")
    entities = relationship("CodeEntity", cascade="all, delete-orphan")
    relations = relationship("CodeRelation", cascade="all, delete-orphan")
    issues = relationship("ScanIssue", cascade="all, delete-orphan")
```

```python
# backend/app/models/code_file.py
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CodeFile(Base):
    __tablename__ = "code_files"
    __table_args__ = (UniqueConstraint("project_id", "file_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str] = mapped_column(String(32))
    line_count: Mapped[int]
    file_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
```

```python
# backend/app/models/code_entity.py
from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CodeEntity(Base):
    __tablename__ = "code_entities"
    __table_args__ = (UniqueConstraint("project_id", "entity_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("code_files.id", ondelete="CASCADE"), index=True)
    entity_key: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str]
    name: Mapped[str]
    qualified_name: Mapped[str]
    file_path: Mapped[str] = mapped_column(Text)
    start_line: Mapped[int]
    end_line: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
```

```python
# backend/app/models/code_relation.py
from sqlalchemy import Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CodeRelation(Base):
    __tablename__ = "code_relations"
    __table_args__ = (
        UniqueConstraint("project_id", "source_id", "target_id", "relation_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("code_entities.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("code_entities.id", ondelete="CASCADE"))
    relation_type: Mapped[str]
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
```

```python
# backend/app/models/scan_issue.py
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScanIssue(Base):
    __tablename__ = "scan_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(Text)
    issue_type: Mapped[str]
    reason_code: Mapped[str]
    message: Mapped[str] = mapped_column(Text)
```

Export every model from `backend/app/models/__init__.py` so SQLAlchemy imports all tables before `create_all`.

- [ ] **Step 5: Initialize tables during application startup**

Add a FastAPI lifespan function that runs `Base.metadata.create_all(engine)` and pass it to `FastAPI(lifespan=lifespan)`.

- [ ] **Step 6: Verify models and existing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py tests/test_health.py -v
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```powershell
git add backend/app backend/tests
git commit -m "feat: add code ingestion data model"
```

---

### Task 3: Register Projects Through the API

**Files:**
- Create: `backend/app/errors.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/project.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/project_service.py`
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/utils/path_utils.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/project_api.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/integration/test_projects_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add failing API tests**

Tests must verify:

```python
def test_create_project(client, tmp_path):
    response = client.post(
        "/api/projects",
        json={"name": "Demo", "root_path": str(tmp_path)},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "created"
    assert response.json()["root_path"] == str(tmp_path.resolve())


def test_create_project_rejects_missing_directory(client, tmp_path):
    response = client.post(
        "/api/projects",
        json={"name": "Missing", "root_path": str(tmp_path / "missing")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ROOT_PATH"


def test_create_project_rejects_duplicate_root(client, tmp_path):
    payload = {"name": "One", "root_path": str(tmp_path)}
    assert client.post("/api/projects", json=payload).status_code == 201
    response = client.post("/api/projects", json={**payload, "name": "Two"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROJECT_ROOT_EXISTS"
```

`conftest.py` must create a temporary SQLite file, override `get_session`, call `Base.metadata.create_all`, and yield `TestClient(app)`.

- [ ] **Step 2: Run and verify route failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_projects_api.py -v
```

Expected: all tests fail because `/api/projects` does not exist.

- [ ] **Step 3: Implement stable errors and path validation**

```python
# backend/app/errors.py
class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
```

```python
# backend/app/utils/path_utils.py
from pathlib import Path

from app.errors import DomainError


def normalize_project_root(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise DomainError("INVALID_ROOT_PATH", f"Not a directory: {value}", 422)
    return path
```

- [ ] **Step 4: Implement schema, service, and route**

```python
# backend/app/schemas/project.py
from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    root_path: str = Field(min_length=1)


class ProjectRead(BaseModel):
    id: int
    name: str
    root_path: str
    status: str
    model_config = ConfigDict(from_attributes=True)
```

`ProjectService.create()` normalizes the path, checks `Project.root_path`, raises `PROJECT_ROOT_EXISTS` with status `409`, inserts the project, commits, and refreshes it.

The route uses `Depends(get_session)`, returns `ProjectRead`, and declares status `201`.

Register one application-level `DomainError` handler:

```python
@app.exception_handler(DomainError)
async def domain_error_handler(_, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )
```

- [ ] **Step 5: Verify project API behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_projects_api.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```powershell
git add backend/app backend/tests
git commit -m "feat: add project registration API"
```

---

### Task 4: Implement Safe Project Scanning

**Files:**
- Create: `backend/app/services/scanner.py`
- Create: `backend/app/utils/hash_utils.py`
- Create: `backend/tests/unit/test_scanner.py`

- [ ] **Step 1: Write scanner tests**

Cover these concrete cases:

```python
def test_scanner_discovers_supported_files_and_ignores_build_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text("class App {}\n", encoding="utf-8")
    (tmp_path / "src" / "config.yml").write_text("ok: true\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "bad.js").write_text("bad()", encoding="utf-8")

    result = ProjectScanner(max_source_bytes=1024).scan(tmp_path)

    assert [item.file_path for item in result.files] == ["src/App.java", "src/config.yml"]
    assert result.issues == ()


def test_scanner_records_binary_and_oversized_files(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"\x00binary")
    (tmp_path / "large.py").write_text("x" * 20, encoding="utf-8")

    result = ProjectScanner(max_source_bytes=10).scan(tmp_path)

    assert result.files == ()
    assert {issue.reason_code for issue in result.issues} == {"BINARY_FILE", "FILE_TOO_LARGE"}
```

Also test UTF-8 BOM, deterministic POSIX paths, empty-file line count `0`, and SHA-256.

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_scanner.py -v
```

Expected: import failure for `ProjectScanner`.

- [ ] **Step 3: Implement scanner DTOs and helpers**

```python
@dataclass(frozen=True, slots=True)
class ScannedFile:
    file_path: str
    language: str
    content: str
    line_count: int
    file_hash: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ScanIssueCandidate:
    file_path: str
    issue_type: str
    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    files: tuple[ScannedFile, ...]
    issues: tuple[ScanIssueCandidate, ...]
```

Implement `ProjectScanner.scan(root: Path) -> ScanResult` with the exact ignore list and extension map from the design. Sort candidate paths by `relative_path.as_posix()` before reading. Reject directory symlinks and record file symlinks as `SYMLINK_FILE`.

- [ ] **Step 4: Verify scanner behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_scanner.py -v
```

Expected: all scanner tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/scanner.py backend/app/utils backend/tests/unit/test_scanner.py
git commit -m "feat: add safe project scanner"
```

---

### Task 5: Define Parser Contracts and API Normalization

**Files:**
- Create: `backend/app/parsers/__init__.py`
- Create: `backend/app/parsers/base.py`
- Create: `backend/app/utils/api_normalizer.py`
- Create: `backend/tests/unit/test_api_normalizer.py`

- [ ] **Step 1: Write normalization tests**

```python
import pytest

from app.utils.api_normalizer import normalize_api_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/api/user/{id}", "/api/user/{param}"),
        ("/api/user/:id", "/api/user/{param}"),
        ("/api/user/${id}", "/api/user/{param}"),
        ("/api/user/123?active=true", "/api/user/{param}"),
        ("api//alerts/", "/api/alerts"),
        ("/", "/"),
    ],
)
def test_normalize_api_path(raw: str, expected: str) -> None:
    assert normalize_api_path(raw) == expected
```

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_api_normalizer.py -v
```

Expected: import failure.

- [ ] **Step 3: Implement parser DTOs exactly as declared in Shared Domain Types**

Add a `SourceParser` protocol with `supports(language)` and `parse(file_path, source)`. Add helper functions:

```python
def entity_key(candidate: EntityCandidate) -> str:
    return (
        f"{candidate.entity_type}:{candidate.file_path}:"
        f"{candidate.qualified_name}:{candidate.start_line}"
    )


def source_slice(source: str, start_line: int, end_line: int) -> str:
    return "\n".join(source.splitlines()[start_line - 1 : end_line])
```

- [ ] **Step 4: Implement path normalization**

Use `urllib.parse.urlsplit`, repeated-slash collapse, trailing-slash removal, and full-segment substitutions for `{name}`, `:name`, `${name}`, and digits. Do not replace digits embedded inside names such as `v2`.

- [ ] **Step 5: Verify normalization**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_api_normalizer.py -v
```

Expected: all parameterized cases pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/parsers backend/app/utils/api_normalizer.py backend/tests/unit/test_api_normalizer.py
git commit -m "feat: define parser contracts and API normalization"
```

---

### Task 6: Implement the Python Parser

**Files:**
- Create: `backend/app/parsers/python_parser.py`
- Create: `backend/tests/unit/test_python_parser.py`

- [ ] **Step 1: Write the failing parser test**

Use one source string containing a decorated class, method, async function, nested function, positional-only argument, keyword-only argument, `*args`, and `**kwargs`. Assert exact names:

```python
def test_python_parser_extracts_qualified_entities():
    result = PythonParser().parse("algorithm/detector.py", SOURCE)
    entities = {(e.entity_type, e.qualified_name): e for e in result.entities}

    assert ("python_class", "Detector") in entities
    assert ("python_function", "Detector.predict") in entities
    assert ("python_function", "train") in entities
    assert ("python_function", "train.prepare") in entities
    assert entities[("python_function", "Detector.predict")].metadata["arguments"] == [
        "self", "values", "threshold", "*extra", "**options"
    ]
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_python_parser.py -v
```

Expected: import failure for `PythonParser`.

- [ ] **Step 3: Implement `PythonParser` with `ast.NodeVisitor`**

Maintain a stack of enclosing class and function names. Emit class entities on `ClassDef` and function entities on both `FunctionDef` and `AsyncFunctionDef`. Read `lineno` and `end_lineno`, use `source_slice`, and preserve decorator names with `ast.unparse`.

Create `CONTAINS` candidates from a class to its direct methods. Use each candidate's `local_key` as relation endpoints.

- [ ] **Step 4: Verify Python parsing**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_python_parser.py -v
```

Expected: all Python parser tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/parsers/python_parser.py backend/tests/unit/test_python_parser.py
git commit -m "feat: parse Python code entities"
```

---

### Task 7: Implement the Java and Spring Parser

**Files:**
- Create: `backend/app/parsers/java_parser.py`
- Create: `backend/tests/unit/test_java_parser.py`

- [ ] **Step 1: Write failing Spring parsing tests**

Use fixtures containing:

```java
@RestController
@RequestMapping("/api/alerts")
class AlertController {
    @GetMapping("/{id}")
    Alert getAlert(@PathVariable Long id) { return null; }

    @RequestMapping(value = {"/search", "/query"}, method = RequestMethod.POST)
    List<Alert> search() { return List.of(); }
}
```

Assert one `java_class`, two `java_method`, and three `backend_api` entities. Assert normalized paths `/api/alerts/{param}`, `/api/alerts/search`, and `/api/alerts/query`; methods `GET`, `POST`, and `POST`; and `DEFINES_API` relations to the correct handler.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_java_parser.py -v
```

Expected: import failure for `JavaParser`.

- [ ] **Step 3: Implement tree-sitter traversal**

Load Java with:

```python
from tree_sitter_language_pack import get_parser

parser = get_parser("java")
tree = parser.parse(source.encode("utf-8"))
```

Walk `class_declaration` and `method_declaration` nodes. Extract node text by byte range, convert zero-based tree-sitter rows to one-based lines, and build qualified method names as `ClassName.methodName`.

- [ ] **Step 4: Implement Spring annotation interpretation**

Implement focused helpers that:

- collect annotation nodes immediately attached to a declaration;
- read the first positional string or `value`/`path` strings;
- map shortcut mappings to HTTP methods;
- extract `RequestMethod.X` from `method`;
- use `/` when a mapping has no path;
- combine class and method paths without duplicate slashes.

Do not attempt general Java constant evaluation. Unsupported expressions produce no path rather than a guessed path.

- [ ] **Step 5: Verify Java parsing**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_java_parser.py -v
```

Expected: all Java parser tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/parsers/java_parser.py backend/tests/unit/test_java_parser.py
git commit -m "feat: parse Java and Spring API entities"
```

---

### Task 8: Implement the Vue, JavaScript, and TypeScript Parser

**Files:**
- Create: `backend/app/parsers/vue_parser.py`
- Create: `backend/tests/unit/test_vue_parser.py`

- [ ] **Step 1: Write failing request parsing tests**

Cover:

```typescript
axios.get("/api/alerts/123")
request.post(`/api/alerts/${alertId}`, payload)
request({ url: "/api/alerts/search", method: "POST" })
request({ url: dynamicUrl, method: dynamicMethod })
```

Assert three `frontend_api_call` entities, normalized paths, correct line offsets inside a `.vue` `<script setup lang="ts">`, and omission of the fully dynamic request.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_vue_parser.py -v
```

Expected: import failure for `VueParser`.

- [ ] **Step 3: Implement Vue script extraction**

Use a compiled multiline regex only to locate `<script ...>...</script>` blocks and read `lang`. Calculate `script_start_line` from newlines before the script body. Pass the body to the `javascript` or `typescript` tree-sitter parser.

- [ ] **Step 4: Implement AST-based call recognition**

Walk `call_expression` nodes. Recognize member calls whose object is `axios` or `request` and whose property is a supported HTTP verb. Recognize `request({...})` only when `url` and `method` values are statically readable.

String literals are decoded without `eval`. Template substitutions are replaced with `{param}` only when the surrounding template text is available.

- [ ] **Step 5: Verify frontend parsing**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_vue_parser.py -v
```

Expected: all Vue/JS/TS parser tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/parsers/vue_parser.py backend/tests/unit/test_vue_parser.py
git commit -m "feat: parse frontend API calls"
```

---

### Task 9: Build Parser Dispatch and Cross-Entity Relations

**Files:**
- Create: `backend/app/parsers/registry.py`
- Create: `backend/app/parsers/relation_builder.py`
- Create: `backend/tests/unit/test_relation_builder.py`

- [ ] **Step 1: Write failing relation tests**

Create candidates for:

- frontend `GET /api/alerts/123`;
- backend `GET /api/alerts/{id}`;
- backend `ANY /api/config`;
- an unmatched frontend call.

Assert exact-method matching produces `REQUESTS_API` confidence `1.0`, `ANY` produces `0.8`, and the unmatched call produces no relation.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_relation_builder.py -v
```

Expected: import failure.

- [ ] **Step 3: Implement parser registry**

Instantiate `JavaParser`, `VueParser`, and `PythonParser` once. `ParserRegistry.parse(scanned_file)` returns an empty `ParseResult` for statistical-only languages and delegates supported languages to exactly one parser.

- [ ] **Step 4: Implement relation builder**

Index backend APIs by `(normalized_path, http_method)`. Match exact methods before `ANY`. Deduplicate by `(source_key, target_key, relation_type)`. Combine parser-local `CONTAINS` and `DEFINES_API` relations with cross-parser `REQUESTS_API` relations.

- [ ] **Step 5: Verify relation tests and all parser tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_relation_builder.py tests/unit/test_*parser.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/parsers backend/tests/unit/test_relation_builder.py
git commit -m "feat: dispatch parsers and build API relations"
```

---

### Task 10: Persist a Full Scan Atomically

**Files:**
- Create: `backend/app/schemas/scan.py`
- Create: `backend/app/services/index_service.py`
- Create: `backend/tests/integration/test_scan_service.py`

- [ ] **Step 1: Write failing service integration tests**

Copy `tests/fixtures/sample_project` to `tmp_path`, create a project, and call `IndexService.scan_project(project.id)`. Assert returned counts equal persisted row counts.

Run a second scan and assert counts are unchanged. Delete one fixture source before a third scan and assert its `CodeFile` and entities are removed.

Add a parser stub that raises for one file and assert a `parse_error` issue is persisted while other files are indexed.

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_scan_service.py -v
```

Expected: import failure for `IndexService`.

- [ ] **Step 3: Implement scan response schema**

```python
class ScanSummary(BaseModel):
    project_id: int
    status: Literal["ready"]
    files_indexed: int
    entities_indexed: int
    relations_indexed: int
    files_skipped: int
    parse_errors: int
```

- [ ] **Step 4: Implement `IndexService`**

Use a class-level `dict[int, threading.Lock]`. Acquire without blocking and raise `SCAN_ALREADY_RUNNING` status `409` if unavailable.

Before the replacement transaction:

1. Load and validate the project.
2. Run `ProjectScanner`.
3. Parse readable files, converting parser exceptions to `ScanIssueCandidate`.
4. Build all relation candidates.

Inside one transaction:

1. Delete old relations, entities, files, and issues for the project in that order.
2. Insert `CodeFile` rows and flush to obtain IDs.
3. Insert entities with deterministic `entity_key` and JSON serialized using `sort_keys=True`.
4. Flush and map local keys to database IDs.
5. Insert only relations whose endpoints exist.
6. Insert scan issues.
7. Set status `ready` and `last_scan_at=utc_now()`.

On failure, roll back, mark the project `failed` in a fresh transaction, and re-raise. Always release the lock.

- [ ] **Step 5: Verify atomic replacement behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_scan_service.py -v
```

Expected: all scan service tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/schemas/scan.py backend/app/services/index_service.py backend/tests/integration/test_scan_service.py
git commit -m "feat: persist atomic project scans"
```

---

### Task 11: Expose Scan and Statistics APIs

**Files:**
- Create: `backend/app/schemas/stats.py`
- Create: `backend/tests/integration/test_scan_api.py`
- Modify: `backend/app/api/project_api.py`
- Modify: `backend/app/services/index_service.py`

- [ ] **Step 1: Write failing endpoint tests**

Assert:

```python
scan = client.post(f"/api/projects/{project_id}/scan")
assert scan.status_code == 200
assert scan.json()["status"] == "ready"

stats = client.get(f"/api/projects/{project_id}/stats")
assert stats.status_code == 200
assert stats.json()["total_files"] > 0
assert stats.json()["languages"]["java"] == 2
assert stats.json()["entity_types"]["backend_api"] > 0
```

Also assert both endpoints return `404` and code `PROJECT_NOT_FOUND` for project `99999`.

- [ ] **Step 2: Verify endpoints fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_scan_api.py -v
```

Expected: `404` for unimplemented routes or import failure for the stats schema.

- [ ] **Step 3: Implement deterministic statistics**

```python
class ProjectStats(BaseModel):
    project_id: int
    total_files: int
    total_lines: int
    languages: dict[str, int]
    entity_types: dict[str, int]
    relation_types: dict[str, int]
    backend_api_count: int
    frontend_api_call_count: int
    skipped_files: int
    parse_errors: int
    last_scan_at: datetime | None
```

`IndexService.get_stats()` uses grouped SQL queries and returns dictionaries sorted by key before schema serialization.

- [ ] **Step 4: Add scan and stats routes**

Add:

```python
@router.post("/{project_id}/scan", response_model=ScanSummary)
def scan_project(project_id: int, session: Session = Depends(get_session)) -> ScanSummary:
    return IndexService(session).scan_project(project_id)


@router.get("/{project_id}/stats", response_model=ProjectStats)
def project_stats(project_id: int, session: Session = Depends(get_session)) -> ProjectStats:
    return IndexService(session).get_stats(project_id)
```

- [ ] **Step 5: Verify all API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration -v
```

Expected: all integration tests pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app backend/tests/integration/test_scan_api.py
git commit -m "feat: expose scan and project statistics APIs"
```

---

### Task 12: Add the Stable Sample Project and Final Week 1 Verification

**Files:**
- Create: `backend/tests/fixtures/sample_project/backend/src/AlertController.java`
- Create: `backend/tests/fixtures/sample_project/backend/src/AlertService.java`
- Create: `backend/tests/fixtures/sample_project/frontend/src/AlertView.vue`
- Create: `backend/tests/fixtures/sample_project/frontend/src/api.ts`
- Create: `backend/tests/fixtures/sample_project/algorithm/detector.py`
- Create: `backend/README.md`
- Modify: integration tests to use the fixture

- [ ] **Step 1: Add the deterministic fixture**

The controller defines:

- class path `/api/alerts`;
- `GET /{id}`;
- `POST /search`.

The Vue page calls both APIs. `api.ts` contains one unmatched request. `detector.py` defines `Detector.predict` and async `train`.

- [ ] **Step 2: Add one end-to-end acceptance test**

```python
def test_week1_acceptance_flow(client, sample_project_path):
    created = client.post(
        "/api/projects",
        json={"name": "Sample", "root_path": str(sample_project_path)},
    )
    project_id = created.json()["id"]

    scan = client.post(f"/api/projects/{project_id}/scan")
    stats = client.get(f"/api/projects/{project_id}/stats")

    assert scan.status_code == 200
    assert scan.json()["parse_errors"] == 0
    assert stats.json()["entity_types"]["backend_api"] == 2
    assert stats.json()["entity_types"]["frontend_api_call"] == 3
    assert stats.json()["relation_types"]["REQUESTS_API"] == 2
    assert stats.json()["entity_types"]["python_function"] >= 2
```

- [ ] **Step 3: Document local startup and API verification**

`backend/README.md` must contain these exact commands:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
.\.venv\Scripts\python.exe -m pytest -v
```

Document `RCA_DATABASE_URL` and `RCA_MAX_SOURCE_BYTES`.

- [ ] **Step 4: Run the complete suite with coverage**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing -v
```

Expected:

- all tests pass;
- branch coverage is at least `80%`;
- no unhandled warnings from project code.

- [ ] **Step 5: Run static syntax verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests
```

Expected: exit code `0`.

- [ ] **Step 6: Check repository state and commit**

Run:

```powershell
git diff --check
git status --short
```

Expected: only intended Week 1 fixture, documentation, and test changes are listed; `git diff --check` exits `0`.

```powershell
git add backend
git commit -m "test: verify week 1 code ingestion flow"
```

---

## Spec Coverage Check

| Design requirement | Implemented by |
| --- | --- |
| Health endpoint | Task 1 |
| SQLite schema | Task 2 |
| Project registration and path validation | Task 3 |
| Safe deterministic scanning | Task 4 |
| Parser DTO boundary and API normalization | Task 5 |
| Python parsing | Task 6 |
| Java/Spring parsing | Task 7 |
| Vue/JS/TS request parsing | Task 8 |
| `CONTAINS`, `DEFINES_API`, `REQUESTS_API` | Tasks 6–9 |
| Atomic full replacement and scan issues | Task 10 |
| Scan and stats APIs | Task 11 |
| Stable fixture and final acceptance | Task 12 |
| Repeated scan without duplicates | Task 10 |
| Failure isolation and rollback | Task 10 |

Deferred work from the design remains excluded.
