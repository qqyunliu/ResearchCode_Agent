import shutil
from pathlib import Path

from sqlalchemy import select

from app.core.database import get_session
from app.models import CodeEntity, CodeRelation


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
        "relations_indexed": 10,
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
        "CALLS_METHOD": 1,
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


def test_frontend_request_diagnostics_endpoint_returns_bounded_examples(
    client,
    tmp_path,
) -> None:
    project_id = create_sample_project(client, tmp_path)
    scan = client.post(f"/api/projects/{project_id}/scan")
    response = client.get(
        f"/api/projects/{project_id}/frontend-request-diagnostics",
        params={"limit": 1},
    )

    assert scan.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["identified_calls"] == 3
    assert payload["matched_calls"] == 2
    assert payload["unmatched_calls"] == 1
    assert len(payload["unmatched_examples"]) == 1
    assert len(payload["unresolved_examples"]) == 0


def test_frontend_request_diagnostics_rejects_invalid_limit_and_missing_project(
    client,
) -> None:
    missing = client.get("/api/projects/999/frontend-request-diagnostics")
    invalid = client.get("/api/projects/1/frontend-request-diagnostics?limit=0")

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert invalid.status_code == 422


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


def test_scan_persists_controller_to_service_call(client, tmp_path) -> None:
    project_id = create_sample_project(client, tmp_path)

    scan = client.post(f"/api/projects/{project_id}/scan")

    assert scan.status_code == 200
    session_override = client.app.dependency_overrides[get_session]
    session_iterator = session_override()
    session = next(session_iterator)
    try:
        call_relation = session.scalar(
            select(CodeRelation).where(
                CodeRelation.project_id == project_id,
                CodeRelation.relation_type == "CALLS_METHOD",
            )
        )
        assert call_relation is not None
        source = session.get(CodeEntity, call_relation.source_id)
        target = session.get(CodeEntity, call_relation.target_id)
        assert source is not None
        assert target is not None
        assert source.qualified_name == "AlertController.getAlert"
        assert target.qualified_name == "AlertService.findById"
        assert call_relation.confidence == 0.8
    finally:
        session_iterator.close()


def test_scan_api_resolves_cross_file_request_wrapper(client, tmp_path) -> None:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / "wrapper_project"
    shutil.copytree(source, project_root)
    frontend = project_root / "frontend" / "src"
    (frontend / "Api.js").write_text(
        'const Api = { loadVideo: "/video/loadVideo" }',
        encoding="utf-8",
    )
    (frontend / "Request.js").write_text(
        "const request = (config) => instance.post(config.url)",
        encoding="utf-8",
    )
    (frontend / "View.vue").write_text(
        "<script setup>\nproxy.request({ url: proxy.Api.loadVideo })\n</script>",
        encoding="utf-8",
    )
    (project_root / "backend" / "src" / "VideoController.java").write_text(
        """@RestController
@RequestMapping("/video")
class VideoController {
  @PostMapping("/loadVideo")
  void loadVideo() {}
}""",
        encoding="utf-8",
    )
    project = client.post(
        "/api/projects",
        json={"name": "Wrapper Demo", "root_path": str(project_root)},
    )

    scan = client.post(f"/api/projects/{project.json()['id']}/scan")
    stats = client.get(f"/api/projects/{project.json()['id']}/stats")

    assert scan.status_code == 200
    assert stats.json()["entity_types"]["frontend_api_call"] == 4
    assert stats.json()["relation_types"]["REQUESTS_API"] == 3
