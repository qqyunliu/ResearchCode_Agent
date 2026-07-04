import hashlib
from pathlib import Path

import pytest

from app.services.scanner import ProjectScanner


def test_scanner_discovers_supported_files_and_ignores_build_dirs(
    tmp_path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text(
        "class App {}\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "config.yml").write_text(
        "enabled: true\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "bad.js").write_text(
        "bad()",
        encoding="utf-8",
    )
    (tmp_path / ".pytest_tmp").mkdir()
    (tmp_path / ".pytest_tmp" / "generated.py").write_text(
        "generated = True",
        encoding="utf-8",
    )
    (tmp_path / ".worktrees").mkdir()
    (tmp_path / ".worktrees" / "branch.py").write_text(
        "duplicate = True",
        encoding="utf-8",
    )

    result = ProjectScanner(max_source_bytes=1024).scan(tmp_path)

    assert [item.file_path for item in result.files] == [
        "src/App.java",
        "src/config.yml",
    ]
    assert [item.language for item in result.files] == ["java", "yaml"]
    assert result.issues == ()


def test_scanner_returns_deterministic_posix_paths(tmp_path) -> None:
    (tmp_path / "z.py").write_text("z = 1\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.ts").write_text(
        "const a = 1\n",
        encoding="utf-8",
    )

    result = ProjectScanner(max_source_bytes=1024).scan(tmp_path)

    assert [item.file_path for item in result.files] == [
        "nested/a.ts",
        "z.py",
    ]


def test_scanner_collects_size_lines_hash_and_utf8_bom(tmp_path) -> None:
    raw_content = b"\xef\xbb\xbffirst\nsecond\n"
    (tmp_path / "module.py").write_bytes(raw_content)
    (tmp_path / "empty.py").write_bytes(b"")

    result = ProjectScanner(max_source_bytes=1024).scan(tmp_path)
    files = {item.file_path: item for item in result.files}

    assert files["module.py"].content == "first\nsecond\n"
    assert files["module.py"].line_count == 2
    assert files["module.py"].size_bytes == len(raw_content)
    assert files["module.py"].file_hash == hashlib.sha256(
        raw_content
    ).hexdigest()
    assert files["empty.py"].line_count == 0


def test_scanner_records_binary_oversized_and_decode_issues(tmp_path) -> None:
    (tmp_path / "binary.py").write_bytes(b"\x00binary")
    (tmp_path / "large.py").write_text("x" * 20, encoding="utf-8")
    (tmp_path / "bad.py").write_bytes(b"\xff\xfe\xfa")

    result = ProjectScanner(max_source_bytes=10).scan(tmp_path)

    assert result.files == ()
    assert {
        (issue.file_path, issue.reason_code) for issue in result.issues
    } == {
        ("bad.py", "DECODE_ERROR"),
        ("binary.py", "BINARY_FILE"),
        ("large.py", "FILE_TOO_LARGE"),
    }


def test_scanner_records_read_error_without_losing_other_files(
    tmp_path,
    monkeypatch,
) -> None:
    bad_file = tmp_path / "bad.py"
    good_file = tmp_path / "good.py"
    bad_file.write_text("bad = True\n", encoding="utf-8")
    good_file.write_text("good = True\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def controlled_read_bytes(path: Path) -> bytes:
        if path.name == "bad.py":
            raise PermissionError("denied for test")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", controlled_read_bytes)

    result = ProjectScanner(max_source_bytes=1024).scan(tmp_path)

    assert [item.file_path for item in result.files] == ["good.py"]
    assert len(result.issues) == 1
    assert result.issues[0].file_path == "bad.py"
    assert result.issues[0].reason_code == "READ_ERROR"


def test_scanner_skips_file_symlink(tmp_path) -> None:
    target = tmp_path / "target.py"
    link = tmp_path / "link.py"
    target.write_text("value = 1\n", encoding="utf-8")
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"Symlink creation is unavailable: {error}")

    result = ProjectScanner(max_source_bytes=1024).scan(tmp_path)

    assert [item.file_path for item in result.files] == ["target.py"]
    assert len(result.issues) == 1
    assert result.issues[0].file_path == "link.py"
    assert result.issues[0].reason_code == "SYMLINK_FILE"
