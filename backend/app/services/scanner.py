from dataclasses import dataclass
import os
from pathlib import Path

from app.core.config import get_settings
from app.utils.hash_utils import sha256_bytes

IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".idea",
        ".vscode",
        ".venv",
        ".pytest_tmp",
        ".worktrees",
        "venv",
    }
)

EXTENSION_LANGUAGES = {
    ".java": "java",
    ".py": "python",
    ".vue": "vue",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".sql": "sql",
    ".xml": "xml",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
}


@dataclass(frozen=True, slots=True)
class ScannedFile:
    file_path: str
    language: str
    content: str
    line_count: int
    file_hash: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ScanIssueCandidate:
    file_path: str
    issue_type: str
    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    files: tuple[ScannedFile, ...]
    issues: tuple[ScanIssueCandidate, ...]


class ProjectScanner:
    def __init__(self, max_source_bytes: int | None = None) -> None:
        configured_limit = get_settings().max_source_bytes
        self.max_source_bytes = max_source_bytes or configured_limit
        if self.max_source_bytes <= 0:
            raise ValueError("max_source_bytes must be greater than zero")

    def scan(self, root: Path) -> ScanResult:
        root = root.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Project root is not a directory: {root}")

        candidates = self._discover_files(root)
        files: list[ScannedFile] = []
        issues: list[ScanIssueCandidate] = []

        for path in candidates:
            scanned_file, issue = self._read_file(root, path)
            if scanned_file is not None:
                files.append(scanned_file)
            if issue is not None:
                issues.append(issue)

        return ScanResult(files=tuple(files), issues=tuple(issues))

    def _discover_files(self, root: Path) -> list[Path]:
        candidates: list[Path] = []

        for current_root, directory_names, file_names in os.walk(
            root,
            followlinks=False,
        ):
            current_path = Path(current_root)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in IGNORED_DIRECTORIES
                and not (current_path / name).is_symlink()
            )
            for file_name in file_names:
                path = current_path / file_name
                if path.suffix.lower() in EXTENSION_LANGUAGES:
                    candidates.append(path)

        return sorted(
            candidates,
            key=lambda path: path.relative_to(root).as_posix(),
        )

    def _read_file(
        self,
        root: Path,
        path: Path,
    ) -> tuple[ScannedFile | None, ScanIssueCandidate | None]:
        relative_path = path.relative_to(root).as_posix()

        if path.is_symlink():
            return None, self._issue(
                relative_path,
                "SYMLINK_FILE",
                "Symbolic links are not scanned.",
            )

        try:
            size_bytes = path.stat().st_size
        except OSError as error:
            return None, self._read_error(relative_path, error)

        if size_bytes > self.max_source_bytes:
            return None, self._issue(
                relative_path,
                "FILE_TOO_LARGE",
                (
                    f"File size {size_bytes} exceeds limit "
                    f"{self.max_source_bytes}."
                ),
            )

        try:
            raw_content = path.read_bytes()
        except OSError as error:
            return None, self._read_error(relative_path, error)

        if b"\x00" in raw_content[:8192]:
            return None, self._issue(
                relative_path,
                "BINARY_FILE",
                "A NUL byte was found in the first 8192 bytes.",
            )

        try:
            content = raw_content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            return None, self._issue(
                relative_path,
                "DECODE_ERROR",
                f"File is not valid UTF-8: {error}",
            )

        return (
            ScannedFile(
                file_path=relative_path,
                language=EXTENSION_LANGUAGES[path.suffix.lower()],
                content=content,
                line_count=len(content.splitlines()),
                file_hash=sha256_bytes(raw_content),
                size_bytes=len(raw_content),
            ),
            None,
        )

    @staticmethod
    def _issue(
        file_path: str,
        reason_code: str,
        message: str,
    ) -> ScanIssueCandidate:
        return ScanIssueCandidate(
            file_path=file_path,
            issue_type="skipped",
            reason_code=reason_code,
            message=message,
        )

    def _read_error(
        self,
        file_path: str,
        error: OSError,
    ) -> ScanIssueCandidate:
        return self._issue(
            file_path,
            "READ_ERROR",
            f"File could not be read: {error}",
        )
