from pathlib import Path

from app.errors import DomainError


def normalize_project_root(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise DomainError(
            code="INVALID_ROOT_PATH",
            message=f"Project root is not an existing directory: {value}",
            status_code=422,
        )
    return path
