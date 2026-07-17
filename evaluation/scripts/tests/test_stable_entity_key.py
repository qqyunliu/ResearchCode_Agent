#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for stable_entity_key.py.

Run with:
    python -m pytest tests/test_stable_entity_key.py -v

Or from the project root:
    backend\\.venv\\python.exe -m pytest evaluation/scripts/tests/test_stable_entity_key.py -v
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import unittest

# Ensure the scripts directory is importable.
_SCRIPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from stable_entity_key import (
    compute_stable_key,
    compute_stable_key_from_dict,
    _normalize_file_path,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_BASE_ARGS = dict(
    repo_id="ruoyi-vue",
    commit_sha="41720e624c5a668c7d3777835e4c87095a7a1dfd",
    file_path="ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    entity_type="class",
    qualified_name="com.ruoyi.web.controller.system.SysUserController",
    start_line=15,
    end_line=120,
)


def _expected_hex(
    repo_id: str,
    commit_sha: str,
    file_path: str,
    entity_type: str,
    qualified_name: str,
    start_line,
    end_line,
) -> str:
    """Independently compute the expected SHA-256 for verification."""
    normalized = file_path.replace("\\", "/").lower()
    payload = "|".join([
        str(repo_id),
        str(commit_sha),
        normalized,
        str(entity_type),
        str(qualified_name),
        str(int(start_line)),
        str(int(end_line)),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNormalizeFilePath(unittest.TestCase):
    """Tests for the internal path normalization helper."""

    def test_forward_slashes_unchanged(self):
        path = "src/main/java/com/example/Main.java"
        self.assertEqual(
            _normalize_file_path(path),
            "src/main/java/com/example/main.java",
        )

    def test_backslashes_become_forward_slashes(self):
        path = "src\\main\\java\\com\\example\\Main.java"
        self.assertEqual(
            _normalize_file_path(path),
            "src/main/java/com/example/main.java",
        )

    def test_mixed_separators(self):
        path = "src/main\\java/com\\example/Main.java"
        self.assertEqual(
            _normalize_file_path(path),
            "src/main/java/com/example/main.java",
        )

    def test_uppercase_lowered(self):
        path = "Src/Main/JAVA/Com/Example/Main.Java"
        self.assertEqual(
            _normalize_file_path(path),
            "src/main/java/com/example/main.java",
        )


class TestComputeStableKey(unittest.TestCase):
    """Core key-computation tests."""

    def test_deterministic_same_input_same_output(self):
        """Same inputs must always produce the same hex digest."""
        key1 = compute_stable_key(**_BASE_ARGS)
        key2 = compute_stable_key(**_BASE_ARGS)
        self.assertEqual(key1, key2)
        self.assertEqual(len(key1), 64)  # SHA-256 hex length

    def test_matches_independent_computation(self):
        """The function output must match a manually computed SHA-256."""
        key = compute_stable_key(**_BASE_ARGS)
        expected = _expected_hex(**_BASE_ARGS)
        self.assertEqual(key, expected)

    def test_path_normalization_backslashes(self):
        """Backslash paths and forward-slash paths must produce the same key."""
        args_fwd = dict(_BASE_ARGS)
        args_bwd = dict(_BASE_ARGS)
        args_bwd["file_path"] = args_bwd["file_path"].replace("/", "\\")

        key_fwd = compute_stable_key(**args_fwd)
        key_bwd = compute_stable_key(**args_bwd)
        self.assertEqual(key_fwd, key_bwd)

    def test_case_normalization_paths_lowered(self):
        """Uppercase and lowercase paths must produce the same key."""
        args_lower = dict(_BASE_ARGS)
        args_upper = dict(_BASE_ARGS)
        args_upper["file_path"] = args_upper["file_path"].upper()

        key_lower = compute_stable_key(**args_lower)
        key_upper = compute_stable_key(**args_upper)
        self.assertEqual(key_lower, key_upper)

    def test_different_repo_id_produces_different_key(self):
        args2 = dict(_BASE_ARGS, repo_id="jeecg-boot")
        self.assertNotEqual(
            compute_stable_key(**_BASE_ARGS),
            compute_stable_key(**args2),
        )

    def test_different_commit_sha_produces_different_key(self):
        args2 = dict(_BASE_ARGS, commit_sha="a" * 40)
        self.assertNotEqual(
            compute_stable_key(**_BASE_ARGS),
            compute_stable_key(**args2),
        )

    def test_different_file_path_produces_different_key(self):
        args2 = dict(_BASE_ARGS, file_path="src/Other.java")
        self.assertNotEqual(
            compute_stable_key(**_BASE_ARGS),
            compute_stable_key(**args2),
        )

    def test_different_entity_type_produces_different_key(self):
        args2 = dict(_BASE_ARGS, entity_type="method")
        self.assertNotEqual(
            compute_stable_key(**_BASE_ARGS),
            compute_stable_key(**args2),
        )

    def test_different_qualified_name_produces_different_key(self):
        args2 = dict(_BASE_ARGS, qualified_name="com.other.Foo")
        self.assertNotEqual(
            compute_stable_key(**_BASE_ARGS),
            compute_stable_key(**args2),
        )

    def test_different_start_line_produces_different_key(self):
        args2 = dict(_BASE_ARGS, start_line=16)
        self.assertNotEqual(
            compute_stable_key(**_BASE_ARGS),
            compute_stable_key(**args2),
        )

    def test_different_end_line_produces_different_key(self):
        args2 = dict(_BASE_ARGS, end_line=121)
        self.assertNotEqual(
            compute_stable_key(**_BASE_ARGS),
            compute_stable_key(**args2),
        )

    def test_no_trailing_newline_affects_hash(self):
        """The payload must not contain a trailing newline.

        We verify this by computing the hash with and without a newline
        and confirming the function matches the no-newline version.
        """
        key = compute_stable_key(**_BASE_ARGS)
        expected_no_newline = _expected_hex(**_BASE_ARGS)

        # Build a payload WITH a trailing newline -- this must NOT match.
        normalized = _BASE_ARGS["file_path"].replace("\\", "/").lower()
        payload_with_newline = "|".join([
            _BASE_ARGS["repo_id"],
            _BASE_ARGS["commit_sha"],
            normalized,
            _BASE_ARGS["entity_type"],
            _BASE_ARGS["qualified_name"],
            str(_BASE_ARGS["start_line"]),
            str(_BASE_ARGS["end_line"]),
        ]) + "\n"
        wrong_hash = hashlib.sha256(
            payload_with_newline.encode("utf-8")
        ).hexdigest()

        self.assertEqual(key, expected_no_newline)
        self.assertNotEqual(key, wrong_hash)

    def test_string_line_numbers_accepted(self):
        """Line numbers may arrive as strings (e.g. from JSON)."""
        args_str = dict(_BASE_ARGS, start_line="15", end_line="120")
        key_int = compute_stable_key(**_BASE_ARGS)
        key_str = compute_stable_key(**args_str)
        self.assertEqual(key_int, key_str)


class TestComputeStableKeyFromDict(unittest.TestCase):
    """Tests for the dict-based convenience wrapper."""

    def test_same_as_positional(self):
        key_dict = compute_stable_key_from_dict(_BASE_ARGS)
        key_pos = compute_stable_key(**_BASE_ARGS)
        self.assertEqual(key_dict, key_pos)

    def test_missing_field_raises_key_error(self):
        incomplete = {k: v for k, v in _BASE_ARGS.items() if k != "end_line"}
        with self.assertRaises(KeyError):
            compute_stable_key_from_dict(incomplete)

    def test_extra_fields_ignored(self):
        extra = dict(_BASE_ARGS, extra_field="ignored")
        key = compute_stable_key_from_dict(extra)
        expected = compute_stable_key(**_BASE_ARGS)
        self.assertEqual(key, expected)


class TestCLI(unittest.TestCase):
    """Test the CLI interface via subprocess."""

    @classmethod
    def setUpClass(cls):
        # Locate the Python interpreter and the script.
        cls.python = sys.executable
        cls.script = os.path.join(_SCRIPTS_DIR, "stable_entity_key.py")

    def _run_cli(self, **overrides) -> subprocess.CompletedProcess:
        args = dict(_BASE_ARGS)
        args.update(overrides)
        cmd = [
            self.python,
            self.script,
            "--repo-id", args["repo_id"],
            "--commit-sha", args["commit_sha"],
            "--file-path", args["file_path"],
            "--entity-type", args["entity_type"],
            "--qualified-name", args["qualified_name"],
            "--start-line", str(args["start_line"]),
            "--end-line", str(args["end_line"]),
        ]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_cli_produces_correct_key(self):
        result = self._run_cli()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        expected = compute_stable_key(**_BASE_ARGS)
        self.assertEqual(result.stdout.strip(), expected)

    def test_cli_help_flag(self):
        cmd = [self.python, self.script, "--help"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("stable entity key", result.stdout.lower())

    def test_cli_missing_arg_fails(self):
        cmd = [self.python, self.script, "--repo-id", "test"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_output_is_64_hex_chars(self):
        result = self._run_cli()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = result.stdout.strip()
        self.assertEqual(len(output), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in output))


if __name__ == "__main__":
    unittest.main()
