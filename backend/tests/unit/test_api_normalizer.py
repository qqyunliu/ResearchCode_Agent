import pytest

from app.utils.api_normalizer import normalize_api_path


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("/api/user/{id}", "/api/user/{param}"),
        ("/api/user/:id", "/api/user/{param}"),
        ("/api/user/${id}", "/api/user/{param}"),
        ("/api/user/123", "/api/user/{param}"),
        ("/api/user/123?active=true#result", "/api/user/{param}"),
        ("api//alerts/", "/api/alerts"),
        ("/api/v2/alerts", "/api/v2/alerts"),
        ("/", "/"),
        ("", "/"),
    ],
)
def test_normalize_api_path(raw_path: str, expected: str) -> None:
    assert normalize_api_path(raw_path) == expected


def test_normalize_api_path_uses_path_from_absolute_url() -> None:
    assert (
        normalize_api_path("https://example.test/api/alerts/42?full=true")
        == "/api/alerts/{param}"
    )
