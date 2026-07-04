import shutil
from pathlib import Path


def create_sample_project(client, tmp_path) -> int:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / "sample_project"
    shutil.copytree(source, project_root)
    response = client.post(
        "/api/projects",
        json={
            "name": "API Scan Demo",
            "root_path": str(project_root),
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_scan_and_stats_endpoints(client, tmp_path) -> None:
    project_id = create_sample_project(client, tmp_path)

    scan = client.post(f"/api/projects/{project_id}/scan")
    stats = client.get(f"/api/projects/{project_id}/stats")

    assert scan.status_code == 200
    assert scan.json() == {
        "project_id": project_id,
        "status": "ready",
        "files_indexed": 5,
        "entities_indexed": 13,
        "relations_indexed": 9,
        "files_skipped": 0,
        "parse_errors": 0,
    }
    assert stats.status_code == 200
    assert stats.json()["total_files"] == 5
    assert stats.json()["languages"] == {
        "java": 2,
        "python": 1,
        "typescript": 1,
        "vue": 1,
    }
    assert stats.json()["entity_types"]["backend_api"] == 2
    assert stats.json()["entity_types"]["frontend_api_call"] == 3
    assert stats.json()["relation_types"] == {
        "CONTAINS": 5,
        "DEFINES_API": 2,
        "REQUESTS_API": 2,
    }
    assert stats.json()["last_scan_at"] is not None


def test_scan_and_stats_return_project_not_found(client) -> None:
    scan = client.post("/api/projects/99999/scan")
    stats = client.get("/api/projects/99999/stats")

    assert scan.status_code == 404
    assert scan.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert stats.status_code == 404
    assert stats.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_week1_acceptance_flow(client, tmp_path) -> None:
    project_id = create_sample_project(client, tmp_path)

    scan = client.post(f"/api/projects/{project_id}/scan")
    stats = client.get(f"/api/projects/{project_id}/stats")

    assert scan.status_code == 200
    assert scan.json()["parse_errors"] == 0
    assert stats.status_code == 200
    assert stats.json()["entity_types"]["backend_api"] == 2
    assert stats.json()["entity_types"]["frontend_api_call"] == 3
    assert stats.json()["relation_types"]["REQUESTS_API"] == 2
    assert stats.json()["entity_types"]["python_function"] >= 2
