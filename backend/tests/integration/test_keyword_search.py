import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, CodeEntity, CodeFile, Project
from app.retrieval.keyword_search import KeywordSearchService


@pytest.fixture
def session(tmp_path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'keyword.db').as_posix()}"
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as database_session:
        yield database_session
    engine.dispose()


def add_project(session: Session, root_path: str) -> Project:
    project = Project(
        name=root_path,
        root_path=root_path,
        status="ready",
    )
    session.add(project)
    session.flush()
    return project


def add_entity(
    session: Session,
    project: Project,
    *,
    name: str,
    qualified_name: str = "Demo.other",
    file_path: str = "src/Demo.java",
    content: str = "void other() {}",
    metadata_json: str = "{}",
) -> CodeEntity:
    code_file = CodeFile(
        project_id=project.id,
        file_path=f"{file_path}#{name}",
        language="java",
        line_count=1,
        file_hash=f"{project.id:02d}{name}".ljust(64, "0")[:64],
        size_bytes=len(content),
    )
    session.add(code_file)
    session.flush()
    entity = CodeEntity(
        project_id=project.id,
        file_id=code_file.id,
        entity_key=f"{project.id}:{name}:{code_file.id}",
        entity_type="java_method",
        name=name,
        qualified_name=qualified_name,
        file_path=file_path,
        start_line=1,
        end_line=1,
        content=content,
        metadata_json=metadata_json,
    )
    session.add(entity)
    session.flush()
    return entity


def test_keyword_search_ranks_fields_and_isolates_projects(
    session,
) -> None:
    project = add_project(session, "project-one")
    other_project = add_project(session, "project-two")
    exact = add_entity(session, project, name="NEEDLE")
    qualified = add_entity(
        session,
        project,
        name="qualified",
        qualified_name="Demo.needleHandler",
    )
    name_contains = add_entity(session, project, name="findNeedle")
    file_contains = add_entity(
        session,
        project,
        name="file",
        file_path="src/needle/Demo.java",
    )
    content_contains = add_entity(
        session,
        project,
        name="content",
        content="return needle;",
    )
    add_entity(session, other_project, name="needle")
    session.commit()

    hits = KeywordSearchService(session).search(
        project.id,
        "needle",
        limit=10,
    )

    assert [hit.entity_id for hit in hits] == [
        exact.id,
        qualified.id,
        name_contains.id,
        file_contains.id,
        content_contains.id,
    ]
    assert [hit.score for hit in hits] == [
        1.0,
        0.9,
        0.75,
        0.6,
        0.4,
    ]
    assert {hit.source for hit in hits} == {"keyword"}


def test_api_path_metadata_match_and_limit_are_deterministic(
    session,
) -> None:
    project = add_project(session, "api-project")
    first = add_entity(
        session,
        project,
        name="first",
        metadata_json='{"path": "/api/alerts"}',
    )
    second = add_entity(
        session,
        project,
        name="second",
        metadata_json='{"normalized_path": "/api/alerts/{param}"}',
    )
    session.commit()

    hits = KeywordSearchService(session).search(
        project.id,
        "/api/alerts",
        limit=1,
    )

    assert [hit.entity_id for hit in hits] == [first.id]
    assert hits[0].score == 0.85
    assert hits[0].metadata == {"path": "/api/alerts"}
    assert second.id > first.id


def test_sql_wildcards_are_matched_as_literal_text(session) -> None:
    project = add_project(session, "wildcard-project")
    literal = add_entity(session, project, name="%")
    add_entity(session, project, name="ordinary")
    session.commit()

    hits = KeywordSearchService(session).search(
        project.id,
        "%",
        limit=10,
    )

    assert [hit.entity_id for hit in hits] == [literal.id]


def create_scanned_project(client, tmp_path) -> int:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / "keyword_api_project"
    shutil.copytree(source, project_root)
    created = client.post(
        "/api/projects",
        json={
            "name": "Keyword API Demo",
            "root_path": str(project_root),
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    scanned = client.post(f"/api/projects/{project_id}/scan")
    assert scanned.status_code == 200
    return project_id


def test_keyword_search_endpoint(client, tmp_path) -> None:
    project_id = create_scanned_project(client, tmp_path)

    response = client.post(
        "/api/search/keyword",
        json={
            "project_id": project_id,
            "query": "getAlert",
            "limit": 2,
        },
    )

    assert response.status_code == 200
    hits = response.json()
    assert len(hits) == 2
    assert hits[0]["name"] == "getAlert"
    assert hits[0]["score"] == 1.0
    assert hits[0]["source"] == "keyword"


def test_keyword_search_validates_request_and_project(client) -> None:
    blank = client.post(
        "/api/search/keyword",
        json={"project_id": 1, "query": "   ", "limit": 10},
    )
    missing = client.post(
        "/api/search/keyword",
        json={"project_id": 99999, "query": "alert", "limit": 10},
    )

    assert blank.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
