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
    assert response.json()["sort_order"] == 0
    assert response.json()["path_accessible"] is True


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
from app.core.dependencies import get_vector_store
from app.main import app
from app.models import CodeEntity, CodeFile, Project


class FakeVectorStore:
    def __init__(self, fail: bool = False) -> None:
        self.deleted: list[int] = []
        self.fail = fail

    def delete_project_collection(self, project_id: int) -> None:
        if self.fail:
            raise RuntimeError("qdrant unavailable")
        self.deleted.append(project_id)


def test_list_projects_reports_order_and_path_accessibility(
    client, tmp_path
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    client.post("/api/projects", json={"name": "First", "root_path": str(first)})
    client.post("/api/projects", json={"name": "Second", "root_path": str(second)})
    second.rmdir()
    response = client.get("/api/projects")
    assert [item["name"] for item in response.json()] == ["Second", "First"]
    assert [item["sort_order"] for item in response.json()] == [0, 1]
    assert [item["path_accessible"] for item in response.json()] == [False, True]


def test_reorder_projects_persists_and_rejects_conflict(client, tmp_path) -> None:
    for name in ("one", "two", "three"):
        path = tmp_path / name
        path.mkdir()
        client.post("/api/projects", json={"name": name, "root_path": str(path)})
    ids = [item["id"] for item in reversed(client.get("/api/projects").json())]
    response = client.put("/api/projects/order", json={"project_ids": ids})
    assert [item["id"] for item in response.json()] == ids
    conflict = client.put(
        "/api/projects/order", json={"project_ids": [ids[0], ids[0]]}
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "PROJECT_ORDER_CONFLICT"


def test_delete_project_cleans_vector_collection_and_database(
    client, tmp_path
) -> None:
    store = FakeVectorStore()
    app.dependency_overrides[get_vector_store] = lambda: store
    project = client.post(
        "/api/projects", json={"name": "Delete", "root_path": str(tmp_path)}
    ).json()
    response = client.delete(f"/api/projects/{project['id']}")
    assert response.status_code == 204
    assert store.deleted == [project["id"]]
    assert client.get("/api/projects").json() == []


def test_delete_project_keeps_row_when_vector_cleanup_fails(
    client, tmp_path
) -> None:
    app.dependency_overrides[get_vector_store] = lambda: FakeVectorStore(True)
    project = client.post(
        "/api/projects", json={"name": "Keep", "root_path": str(tmp_path)}
    ).json()
    response = client.delete(f"/api/projects/{project['id']}")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "VECTOR_STORE_DELETE_FAILED"
    assert client.get("/api/projects").json()[0]["id"] == project["id"]
