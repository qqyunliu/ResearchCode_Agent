import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.graph.query_service import GraphQueryService
from app.models import Base, CodeEntity, CodeFile, CodeRelation, Project


@pytest.fixture
def graph_session(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'graph.db').as_posix()}"
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        project = Project(name="Graph", root_path=str(tmp_path / "graph"))
        other = Project(name="Other", root_path=str(tmp_path / "other"))
        session.add_all([project, other])
        session.flush()
        source_file = CodeFile(
            project_id=project.id,
            file_path="src/Alert.java",
            language="java",
            line_count=20,
            file_hash="a" * 64,
            size_bytes=100,
        )
        other_file = CodeFile(
            project_id=other.id,
            file_path="src/Other.java",
            language="java",
            line_count=1,
            file_hash="b" * 64,
            size_bytes=10,
        )
        session.add_all([source_file, other_file])
        session.flush()

        def node(
            key: str,
            entity_type: str,
            name: str,
            metadata: dict[str, object],
        ) -> CodeEntity:
            return CodeEntity(
                project_id=project.id,
                file_id=source_file.id,
                entity_key=key,
                entity_type=entity_type,
                name=name,
                qualified_name=name,
                file_path=source_file.file_path,
                start_line=1,
                end_line=2,
                content=name,
                metadata_json=json.dumps(metadata),
            )

        frontend = node(
            "frontend",
            "frontend_api_call",
            "GET /api/alerts/${id}",
            {},
        )
        api = node(
            "api",
            "backend_api",
            "GET /api/alerts/{id}",
            {
                "http_method": "GET",
                "normalized_path": "/api/alerts/{param}",
            },
        )
        controller = node(
            "controller",
            "java_method",
            "AlertController.getAlert",
            {},
        )
        service = node(
            "service",
            "java_method",
            "AlertService.findById",
            {},
        )
        session.add_all([frontend, api, controller, service])
        session.flush()
        session.add_all(
            [
                CodeRelation(
                    project_id=project.id,
                    source_id=frontend.id,
                    target_id=api.id,
                    relation_type="REQUESTS_API",
                    confidence=1.0,
                    metadata_json="{}",
                ),
                CodeRelation(
                    project_id=project.id,
                    source_id=api.id,
                    target_id=controller.id,
                    relation_type="DEFINES_API",
                    confidence=1.0,
                    metadata_json="{}",
                ),
                CodeRelation(
                    project_id=project.id,
                    source_id=controller.id,
                    target_id=service.id,
                    relation_type="CALLS_METHOD",
                    confidence=0.8,
                    metadata_json='{"resolution":"receiver_type"}',
                ),
                CodeRelation(
                    project_id=project.id,
                    source_id=service.id,
                    target_id=api.id,
                    relation_type="TEST_CYCLE",
                    confidence=0.5,
                    metadata_json="{}",
                ),
            ]
        )
        other_entity = CodeEntity(
            project_id=other.id,
            file_id=other_file.id,
            entity_key="other",
            entity_type="java_method",
            name="Other.method",
            qualified_name="Other.method",
            file_path=other_file.file_path,
            start_line=1,
            end_line=1,
            content="other",
            metadata_json="{}",
        )
        session.add(other_entity)
        session.commit()
        yield session, project, frontend, api, controller, service, other_entity
    engine.dispose()


def test_depth_zero_returns_only_seed(graph_session) -> None:
    session, project, _, api, _, _, _ = graph_session

    result = GraphQueryService(session).traverse(
        project.id,
        api.id,
        max_depth=0,
    )

    assert [node.entity_id for node in result.nodes] == [api.id]
    assert result.edges == ()


def test_bfs_traverses_incoming_and_outgoing_edges_by_depth(
    graph_session,
) -> None:
    session, project, frontend, api, controller, service, _ = graph_session
    graph = GraphQueryService(session)

    depth_one = graph.traverse(project.id, api.id, max_depth=1)
    depth_two = graph.traverse(project.id, api.id, max_depth=2)

    assert [node.entity_id for node in depth_one.nodes] == [
        api.id,
        frontend.id,
        controller.id,
        service.id,
    ]
    assert {edge.relation_type for edge in depth_one.edges} == {
        "REQUESTS_API",
        "DEFINES_API",
        "TEST_CYCLE",
    }
    assert [node.entity_id for node in depth_two.nodes] == [
        api.id,
        frontend.id,
        controller.id,
        service.id,
    ]
    assert len({node.entity_id for node in depth_two.nodes}) == 4


def test_relation_filter_limits_expansion(graph_session) -> None:
    session, project, _, api, controller, _, _ = graph_session

    result = GraphQueryService(session).traverse(
        project.id,
        api.id,
        max_depth=2,
        relation_types=("DEFINES_API",),
    )

    assert [node.entity_id for node in result.nodes] == [
        api.id,
        controller.id,
    ]
    assert [edge.relation_type for edge in result.edges] == [
        "DEFINES_API"
    ]


def test_project_scope_rejects_foreign_or_missing_seed(graph_session) -> None:
    session, project, _, _, _, _, other = graph_session
    graph = GraphQueryService(session)

    with pytest.raises(DomainError) as error:
        graph.traverse(project.id, other.id, max_depth=1)

    assert error.value.code == "ENTITY_NOT_FOUND"
    assert error.value.status_code == 404


def test_exact_api_chain_normalizes_path_and_excludes_cycle(
    graph_session,
) -> None:
    session, project, frontend, api, controller, service, _ = graph_session

    result = GraphQueryService(session).find_api_chain(
        project.id,
        "get",
        "/api/alerts/123",
    )

    assert [node.entity_id for node in result.nodes] == [
        api.id,
        frontend.id,
        controller.id,
        service.id,
    ]
    assert {edge.relation_type for edge in result.edges} == {
        "REQUESTS_API",
        "DEFINES_API",
        "CALLS_METHOD",
    }


def test_exact_api_chain_returns_not_found(graph_session) -> None:
    session, project, *_ = graph_session

    with pytest.raises(DomainError) as error:
        GraphQueryService(session).find_api_chain(
            project.id,
            "DELETE",
            "/api/missing",
        )

    assert error.value.code == "API_NOT_FOUND"
    assert error.value.status_code == 404
