import pytest

from app.errors import DomainError
from app.utils.path_utils import normalize_project_root


def test_normalize_project_root_returns_absolute_directory(tmp_path) -> None:
    normalized = normalize_project_root(str(tmp_path / "." / "child" / ".."))

    assert normalized == tmp_path.resolve()
    assert normalized.is_absolute()


def test_normalize_project_root_rejects_missing_directory(tmp_path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(DomainError) as error:
        normalize_project_root(str(missing_path))

    assert error.value.code == "INVALID_ROOT_PATH"
    assert error.value.status_code == 422
