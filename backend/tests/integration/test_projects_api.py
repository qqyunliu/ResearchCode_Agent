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
