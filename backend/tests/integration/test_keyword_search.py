import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import app.retrieval.keyword_search as keyword_search_module
from app.models import Base, CodeEntity, CodeFile, Project
from app.retrieval.keyword_search import (
    LEXICAL_IMPLEMENTATION_VERSION,
    KeywordSearchService,
)


def test_lexical_implementation_version_is_stable() -> None:
    assert LEXICAL_IMPLEMENTATION_VERSION
    assert LEXICAL_IMPLEMENTATION_VERSION == "code_aware_multiterm_v2"


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


def test_natural_language_query_prioritizes_distinct_term_coverage(
    session,
) -> None:
    project = add_project(session, "natural-language-project")
    both_terms = add_entity(
        session,
        project,
        name="UserLoginHandler",
    )
    one_exact_term = add_entity(
        session,
        project,
        name="user",
    )
    session.commit()

    hits = KeywordSearchService(session).search(
        project.id,
        "user login controller HTTP method path",
        limit=10,
    )

    assert [hit.entity_id for hit in hits] == [
        both_terms.id,
        one_exact_term.id,
    ]
    assert hits[0].score == pytest.approx(0.6)
    assert hits[1].score == pytest.approx(1 / 3)


def test_business_terms_outrank_generic_structure_term_decoy(session) -> None:
    project = add_project(session, "weighted-natural-language-project")
    target = add_entity(session, project, name="UserLoginHandler")
    decoy = add_entity(
        session,
        project,
        name="ControllerHttpMethodPath",
    )
    session.commit()

    hits = KeywordSearchService(session).search(
        project.id,
        "user login controller HTTP method path",
        limit=10,
    )

    assert [hit.entity_id for hit in hits] == [target.id, decoy.id]
    assert hits[0].score == pytest.approx(0.6)
    assert hits[1].score == pytest.approx(0.3)


def test_stopword_only_query_returns_no_hits(session) -> None:
    project = add_project(session, "stopword-project")
    add_entity(session, project, name="whereTheCodeIs")
    session.commit()
    candidate_select_count = 0

    def count_candidate_selects(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        nonlocal candidate_select_count
        normalized_statement = statement.casefold()
        if (
            normalized_statement.lstrip().startswith(("select", "with"))
            and "from code_entities" in normalized_statement
        ):
            candidate_select_count += 1

    event.listen(session.bind, "before_cursor_execute", count_candidate_selects)
    try:
        hits = KeywordSearchService(session).search(
            project.id,
            "where is the",
            limit=10,
        )
    finally:
        event.remove(
            session.bind,
            "before_cursor_execute",
            count_candidate_selects,
        )

    assert hits == []
    assert candidate_select_count == 0


def test_multi_term_search_uses_one_candidate_select(session) -> None:
    project = add_project(session, "one-select-project")
    first = add_entity(session, project, name="UserLoginHandler")
    second = add_entity(session, project, name="UserHandler")
    add_entity(session, project, name="LoginHandler")
    session.commit()
    session.expunge_all()
    candidate_selects: list[str] = []

    def record_candidate_select(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        normalized_statement = statement.casefold()
        if (
            normalized_statement.lstrip().startswith(("select", "with"))
            and "from code_entities" in normalized_statement
        ):
            candidate_selects.append(statement)

    event.listen(session.bind, "before_cursor_execute", record_candidate_select)
    try:
        hits = KeywordSearchService(session).search(
            project.id,
            "user login controller HTTP method path",
            limit=2,
        )
    finally:
        event.remove(
            session.bind,
            "before_cursor_execute",
            record_candidate_select,
        )

    assert [hit.entity_id for hit in hits] == [first.id, second.id]
    assert len(candidate_selects) == 1
    normalized_sql = candidate_selects[0].casefold()
    assert "order by" in normalized_sql
    assert "desc" in normalized_sql
    assert "limit" in normalized_sql


def test_keyword_search_normalizes_unicode_in_sqlite_scoring(session) -> None:
    project = add_project(session, "unicode-project")
    street = add_entity(session, project, name="Straße")
    cafe = add_entity(session, project, name="cafe\u0301")
    session.commit()

    street_hits = KeywordSearchService(session).search(
        project.id,
        "STRASSE",
        limit=10,
    )
    cafe_hits = KeywordSearchService(session).search(
        project.id,
        "café",
        limit=10,
    )

    assert [hit.entity_id for hit in street_hits] == [street.id]
    assert street_hits[0].score == 1.0
    assert [hit.entity_id for hit in cafe_hits] == [cafe.id]
    assert cafe_hits[0].score == 1.0


def test_complete_structured_matches_keep_legacy_priority_and_scores(
    session,
) -> None:
    project = add_project(session, "structured-priority-project")
    exact_identifier = add_entity(session, project, name="getAlert")
    add_entity(session, project, name="get", content="return alert;")
    exact_path = add_entity(
        session,
        project,
        name="alertsEndpoint",
        metadata_json='{"path": "/api/alerts"}',
    )
    add_entity(session, project, name="ApiAlerts")
    exact_file = add_entity(
        session,
        project,
        name="fileHandler",
        file_path="src/UserLoginController.java",
    )
    add_entity(session, project, name="UserLoginController")
    session.commit()

    identifier_hits = KeywordSearchService(session).search(
        project.id,
        "getAlert",
        limit=10,
    )
    path_hits = KeywordSearchService(session).search(
        project.id,
        "/api/alerts",
        limit=10,
    )
    filename_hits = KeywordSearchService(session).search(
        project.id,
        "UserLoginController.java",
        limit=10,
    )

    assert [hit.entity_id for hit in identifier_hits] == [exact_identifier.id]
    assert identifier_hits[0].score == 1.0
    assert [hit.entity_id for hit in path_hits] == [exact_path.id]
    assert path_hits[0].score == 0.85
    assert [hit.entity_id for hit in filename_hits] == [exact_file.id]
    assert filename_hits[0].score == 0.6


def test_sqlite_lexical_score_udf_is_deterministic(session) -> None:
    project = add_project(session, "udf-registration-project")
    add_entity(session, project, name="needle")
    session.commit()

    KeywordSearchService(session).search(project.id, "needle", limit=1)

    functions = session.connection().exec_driver_sql(
        "PRAGMA function_list"
    ).all()
    lexical_function = next(
        row for row in functions if row[0] == "rca_lexical_score"
    )
    assert lexical_function[4] == 6
    assert lexical_function[5] & 0x800


def test_plain_query_scores_each_project_entity_once(
    session,
    monkeypatch,
) -> None:
    project = add_project(session, "plain-udf-count-project")
    add_entity(session, project, name="UserLoginHandler")
    add_entity(session, project, name="UserHandler")
    add_entity(session, project, name="unrelated")
    session.commit()
    call_count = 0
    original_score = keyword_search_module._sqlite_lexical_score

    def counting_score(*args) -> float:
        nonlocal call_count
        call_count += 1
        return original_score(*args)

    monkeypatch.setattr(
        keyword_search_module,
        "_sqlite_lexical_score",
        counting_score,
    )

    KeywordSearchService(session).search(
        project.id,
        "user login",
        limit=1,
    )

    assert call_count == 3


def test_structured_query_scores_each_entity_at_most_twice(
    session,
    monkeypatch,
) -> None:
    project = add_project(session, "structured-udf-count-project")
    add_entity(session, project, name="getHandler", content="return alert;")
    add_entity(session, project, name="alertHandler")
    add_entity(session, project, name="unrelated")
    session.commit()
    call_count = 0
    original_score = keyword_search_module._sqlite_lexical_score

    def counting_score(*args) -> float:
        nonlocal call_count
        call_count += 1
        return original_score(*args)

    monkeypatch.setattr(
        keyword_search_module,
        "_sqlite_lexical_score",
        counting_score,
    )

    hits = KeywordSearchService(session).search(
        project.id,
        "getAlert",
        limit=1,
    )

    assert hits[0].name == "getHandler"
    assert call_count <= 6


@pytest.mark.parametrize("invalid_limit", [0, -1])
def test_non_positive_limit_fails_before_entity_query(
    session,
    invalid_limit,
) -> None:
    project = add_project(session, f"invalid-limit-{invalid_limit}")
    add_entity(session, project, name="needle")
    session.commit()
    entity_selects: list[str] = []

    def record_entity_select(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        if (
            statement.lstrip().casefold().startswith("select")
            and "code_entities" in statement.casefold()
        ):
            entity_selects.append(statement)

    event.listen(session.bind, "before_cursor_execute", record_entity_select)
    try:
        with pytest.raises(ValueError, match="limit"):
            KeywordSearchService(session).search(
                project.id,
                "needle",
                limit=invalid_limit,
            )
    finally:
        event.remove(
            session.bind,
            "before_cursor_execute",
            record_entity_select,
        )

    assert entity_selects == []


@pytest.mark.parametrize("literal", ["%", "_", "\\"])
def test_sql_wildcards_and_escape_are_literal(session, literal) -> None:
    project = add_project(session, f"literal-{ord(literal)}-project")
    exact = add_entity(session, project, name=literal)
    add_entity(session, project, name="ordinary")
    session.commit()

    hits = KeywordSearchService(session).search(
        project.id,
        literal,
        limit=10,
    )

    assert [hit.entity_id for hit in hits] == [exact.id]


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
