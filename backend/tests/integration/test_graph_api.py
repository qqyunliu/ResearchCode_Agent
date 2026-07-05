import shutil
from pathlib import Path

from app.api.graph_api import get_graph_search_service
from app.main import app
from app.retrieval.types import SearchHit


def create_scanned_project(client, tmp_path) -> int:
    source = Path(__file__).parents[1] / "fixtures" / "sample_project"
    project_root = tmp_path / "graph_api_project"
    shutil.copytree(source, project_root)
    created = client.post(
        "/api/projects",
        json={
            "name": "Graph API Demo",
            "root_path": str(project_root),
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    scanned = client.post(f"/api/projects/{project_id}/scan")
    assert scanned.status_code == 200
    return project_id


def test_exact_api_chain_returns_nodes_edges_and_references(
    client,
    tmp_path,
) -> None:
    project_id = create_scanned_project(client, tmp_path)

    response = client.get(
        "/api/graph/api-chain",
        params={
            "project_id": project_id,
            "method": "get",
            "api_path": "/api/alerts/123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["nodes"][0]["entity_type"] == "backend_api"
    assert sorted(
        node["qualified_name"] for node in data["nodes"][1:]
    ) == [
        "AlertController.getAlert",
        "AlertService.findById",
        "GET /api/alerts/${alertId}",
    ]
    assert {edge["relation_type"] for edge in data["edges"]} == {
        "REQUESTS_API",
        "DEFINES_API",
        "CALLS_METHOD",
    }
    assert len(data["references"]) == len(data["nodes"])
    assert data["references"][0]["citation"] == 1
    assert data["references"][0]["file_path"].endswith(
        "AlertController.java"
    )


def test_exact_api_chain_returns_structured_not_found(
    client,
    tmp_path,
) -> None:
    project_id = create_scanned_project(client, tmp_path)

    response = client.get(
        "/api/graph/api-chain",
        params={
            "project_id": project_id,
            "method": "DELETE",
            "api_path": "/api/missing",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "API_NOT_FOUND"


class FakeGraphSearch:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[int, str, int]] = []

    def search(
        self,
        project_id: int,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        self.calls.append((project_id, query, limit))
        return self.hits[:limit]


def test_search_chain_expands_fake_hybrid_hits_without_models(
    client,
    tmp_path,
) -> None:
    project_id = create_scanned_project(client, tmp_path)
    keyword = client.post(
        "/api/search/keyword",
        json={
            "project_id": project_id,
            "query": "getAlert",
            "limit": 1,
        },
    ).json()[0]
    fake = FakeGraphSearch(
        [
            SearchHit(
                **{
                    **keyword,
                    "score": 0.9,
                    "source": "hybrid",
                }
            )
        ]
    )
    app.dependency_overrides[get_graph_search_service] = lambda: fake

    response = client.post(
        "/api/graph/search-chain",
        json={
            "project_id": project_id,
            "query": "Where is getAlert implemented?",
            "limit": 5,
            "max_depth": 2,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert fake.calls == [
        (project_id, "Where is getAlert implemented?", 5)
    ]
    assert len({node["entity_id"] for node in data["nodes"]}) == len(
        data["nodes"]
    )
    assert "CALLS_METHOD" in {
        edge["relation_type"] for edge in data["edges"]
    }


def test_search_chain_validates_query_and_depth(client) -> None:
    app.dependency_overrides[get_graph_search_service] = lambda: (
        FakeGraphSearch([])
    )
    blank = client.post(
        "/api/graph/search-chain",
        json={
            "project_id": 1,
            "query": "   ",
            "max_depth": 2,
        },
    )
    too_deep = client.post(
        "/api/graph/search-chain",
        json={
            "project_id": 1,
            "query": "alerts",
            "max_depth": 3,
        },
    )

    assert blank.status_code == 422
    assert too_deep.status_code == 422
