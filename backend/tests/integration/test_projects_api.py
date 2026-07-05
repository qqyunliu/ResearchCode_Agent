def test_create_project(client, tmp_path) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "Demo",
            "root_path": str(tmp_path),
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "created"
    assert response.json()["root_path"] == str(tmp_path.resolve())


def test_create_project_rejects_missing_directory(client, tmp_path) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "Missing",
            "root_path": str(tmp_path / "missing"),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ROOT_PATH"


def test_create_project_rejects_duplicate_root(client, tmp_path) -> None:
    payload = {
        "name": "One",
        "root_path": str(tmp_path),
    }

    first_response = client.post("/api/projects", json=payload)
    second_response = client.post(
        "/api/projects",
        json={
            **payload,
            "name": "Two",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"]["code"] == "PROJECT_ROOT_EXISTS"


def test_read_project_entity_returns_indexed_code(client, tmp_path) -> None:
    session = next(app.dependency_overrides[get_session]())
    project = Project(name="Demo", root_path=str(tmp_path))
    session.add(project)
    session.flush()
    code_file = CodeFile(
        project_id=project.id,
        file_path="src/AlertController.java",
        language="java",
        line_count=20,
        file_hash="hash",
        size_bytes=200,
    )
    session.add(code_file)
    session.flush()
    entity = CodeEntity(
        project_id=project.id,
        file_id=code_file.id,
        entity_key="method:AlertController.getAlert",
        entity_type="java_method",
        name="getAlert",
        qualified_name="AlertController.getAlert",
        file_path=code_file.file_path,
        start_line=10,
        end_line=13,
        content="return alertService.find();",
        metadata_json="{}",
    )
    session.add(entity)
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/entities/{entity.id}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "entity_id": entity.id,
        "entity_type": "java_method",
        "qualified_name": "AlertController.getAlert",
        "file_path": "src/AlertController.java",
        "start_line": 10,
        "end_line": 13,
        "content": "return alertService.find();",
    }
    session.close()


def test_read_project_entity_rejects_missing_or_foreign_entity(
    client,
    tmp_path,
) -> None:
    session: Session = next(app.dependency_overrides[get_session]())
    first = Project(name="First", root_path=str(tmp_path / "first"))
    second = Project(name="Second", root_path=str(tmp_path / "second"))
    session.add_all([first, second])
    session.flush()
    code_file = CodeFile(
        project_id=first.id,
        file_path="src/demo.py",
        language="python",
        line_count=1,
        file_hash="hash",
        size_bytes=10,
    )
    session.add(code_file)
    session.flush()
    entity = CodeEntity(
        project_id=first.id,
        file_id=code_file.id,
        entity_key="function:demo",
        entity_type="python_function",
        name="demo",
        qualified_name="demo",
        file_path=code_file.file_path,
        start_line=1,
        end_line=1,
        content="def demo(): pass",
        metadata_json="{}",
    )
    session.add(entity)
    session.commit()

    missing = client.get(f"/api/projects/{first.id}/entities/999")
    foreign = client.get(
        f"/api/projects/{second.id}/entities/{entity.id}"
    )

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "ENTITY_NOT_FOUND"
    assert foreign.status_code == 404
    session.close()
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.main import app
from app.models import CodeEntity, CodeFile, Project
