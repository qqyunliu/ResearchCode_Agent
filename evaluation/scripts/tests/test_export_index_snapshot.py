#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for evaluation/scripts/export_index_snapshot.py.

Run with:
    backend\\.venv\\python.exe -m pytest evaluation/scripts/tests/test_export_index_snapshot.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Make the scripts directory importable.
_SCRIPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Make the runners directory importable (for baseline_keyword).
_RUNNERS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "runners")
)
if _RUNNERS_DIR not in sys.path:
    sys.path.insert(0, _RUNNERS_DIR)

# Sample project fixture path.
_FIXTURES_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        os.pardir,
        os.pardir,
        "backend",
        "tests",
        "fixtures",
        "sample_project",
    )
)


# ---------------------------------------------------------------------------
# Unit tests (no backend dependency)
# ---------------------------------------------------------------------------


class TestComputeContentHash(unittest.TestCase):
    """Tests for the content hash function."""

    def test_deterministic(self):
        from export_index_snapshot import compute_content_hash

        h1 = compute_content_hash("class AlertService {}")
        h2 = compute_content_hash("class AlertService {}")
        self.assertEqual(h1, h2)

    def test_different_content_different_hash(self):
        from export_index_snapshot import compute_content_hash

        h1 = compute_content_hash("class AlertService {}")
        h2 = compute_content_hash("class UserService {}")
        self.assertNotEqual(h1, h2)

    def test_sha256_length(self):
        from export_index_snapshot import compute_content_hash

        h = compute_content_hash("test")
        self.assertEqual(len(h), 64)


class TestStableEntityKey(unittest.TestCase):
    """Tests for the stable entity key wrapper."""

    def test_stable_entity_key_wrapper(self):
        from export_index_snapshot import _stable_entity_key

        key = _stable_entity_key(
            repo_id="test-repo",
            commit_sha="a" * 40,
            file_path="src/Main.java",
            entity_type="java_class",
            qualified_name="com.example.Main",
            start_line=1,
            end_line=50,
        )
        self.assertEqual(len(key), 64)

    def test_path_normalization(self):
        from export_index_snapshot import _stable_entity_key

        key_fwd = _stable_entity_key(
            repo_id="test-repo",
            commit_sha="a" * 40,
            file_path="src/main/java/Main.java",
            entity_type="java_class",
            qualified_name="Main",
            start_line=1,
            end_line=10,
        )
        key_bwd = _stable_entity_key(
            repo_id="test-repo",
            commit_sha="a" * 40,
            file_path="src\\main\\java\\Main.java",
            entity_type="java_class",
            qualified_name="Main",
            start_line=1,
            end_line=10,
        )
        self.assertEqual(key_fwd, key_bwd)


# ---------------------------------------------------------------------------
# CLI parser tests
# ---------------------------------------------------------------------------


class TestBuildParser(unittest.TestCase):
    """Tests for the CLI argument parser."""

    def test_help_flag(self):
        from export_index_snapshot import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_required_args(self):
        from export_index_snapshot import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "--db",
                "/tmp/test.db",
                "--repo-id",
                "test-repo",
                "--commit-sha",
                "a" * 40,
                "--output",
                "/tmp/output",
            ]
        )
        self.assertEqual(args.db, Path("/tmp/test.db"))
        self.assertEqual(args.repo_id, "test-repo")
        self.assertEqual(args.commit_sha, "a" * 40)
        self.assertEqual(args.output, Path("/tmp/output"))

    def test_missing_required_args(self):
        from export_index_snapshot import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--db", "/tmp/test.db"])
        self.assertNotEqual(ctx.exception.code, 0)


class TestMainExit(unittest.TestCase):
    """Test the main() function's exit codes."""

    def test_main_invalid_db(self):
        from export_index_snapshot import main

        result = main(
            [
                "--db",
                "/nonexistent/test.db",
                "--repo-id",
                "test",
                "--commit-sha",
                "a" * 40,
                "--output",
                "/tmp/output",
            ]
        )
        self.assertEqual(result, 1)

    def test_main_invalid_commit_sha(self):
        from export_index_snapshot import main

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"")
            f.flush()
            result = main(
                [
                    "--db",
                    f.name,
                    "--repo-id",
                    "test",
                    "--commit-sha",
                    "invalid-sha",
                    "--output",
                    "/tmp/output",
                ]
            )
        os.unlink(f.name)
        self.assertEqual(result, 1)


# ---------------------------------------------------------------------------
# End-to-end tests (require backend dependencies)
# ---------------------------------------------------------------------------


class TestExportEndToEnd(unittest.TestCase):
    """End-to-end test: scan the fixture, then export the snapshot.

    This test first runs baseline_keyword to create a populated DB,
    then runs export_index_snapshot to export it.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.db_path = Path(cls.tmpdir) / "test_export.db"
        cls.output_dir = Path(cls.tmpdir) / "export"
        cls.repo_path = Path(_FIXTURES_DIR)
        cls.dataset_path = Path(cls.tmpdir) / "dataset.json"
        cls.results_path = Path(cls.tmpdir) / "results.jsonl"
        cls.commit_sha = "a" * 40
        cls.repo_id = "sample-project"

        # Create a minimal dataset for the scan.
        dataset = [
            {
                "question_id": "test-0001",
                "question": "AlertService",
                "evaluation_layers": ["retrieval"],
                "task_type": "CODE_QA",
                "language": "en",
            }
        ]
        cls.dataset_path.write_text(
            json.dumps(dataset, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _ensure_db(self):
        """Run baseline_keyword to create a populated DB if needed."""
        if not self.db_path.is_file():
            from baseline_keyword import run_baseline

            run_baseline(
                repo=self.repo_path,
                dataset_path=self.dataset_path,
                db_path=self.db_path,
                output_path=self.results_path,
                top_k=5,
            )

    def test_export_produces_all_files(self):
        """Verify that export creates all expected JSON files."""
        if not self.repo_path.is_dir():
            self.skipTest(
                f"Sample project fixture not found: {self.repo_path}"
            )

        self._ensure_db()

        from export_index_snapshot import run_export

        run_export(
            db_path=self.db_path,
            repo_id=self.repo_id,
            commit_sha=self.commit_sha,
            output_dir=self.output_dir,
        )

        expected_files = [
            "code_files.json",
            "code_entities.json",
            "code_relations.json",
            "scan_issues.json",
            "frontend_diagnostics.json",
            "manifest.json",
        ]
        for fname in expected_files:
            self.assertTrue(
                (self.output_dir / fname).is_file(),
                f"Expected file not found: {fname}",
            )

    def test_export_code_files_content(self):
        """Verify code_files.json has expected structure."""
        if not self.repo_path.is_dir():
            self.skipTest("Sample project fixture not found")

        self._ensure_db()

        from export_index_snapshot import run_export

        if not self.output_dir.is_dir():
            run_export(
                db_path=self.db_path,
                repo_id=self.repo_id,
                commit_sha=self.commit_sha,
                output_dir=self.output_dir,
            )

        data = json.loads(
            (self.output_dir / "code_files.json").read_text(encoding="utf-8")
        )
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        for item in data:
            self.assertIn("file_path", item)
            self.assertIn("language", item)
            self.assertIn("line_count", item)

    def test_export_code_entities_have_stable_keys(self):
        """Verify code_entities.json uses stable entity keys."""
        if not self.repo_path.is_dir():
            self.skipTest("Sample project fixture not found")

        self._ensure_db()

        from export_index_snapshot import run_export

        if not self.output_dir.is_dir():
            run_export(
                db_path=self.db_path,
                repo_id=self.repo_id,
                commit_sha=self.commit_sha,
                output_dir=self.output_dir,
            )

        data = json.loads(
            (self.output_dir / "code_entities.json").read_text(encoding="utf-8")
        )
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        for item in data:
            self.assertIn("stable_entity_key", item)
            self.assertEqual(len(item["stable_entity_key"]), 64)
            self.assertIn("entity_type", item)
            self.assertIn("qualified_name", item)
            self.assertIn("file_path", item)
            self.assertIn("content_hash", item)
            self.assertEqual(len(item["content_hash"]), 64)

    def test_export_manifest_metadata(self):
        """Verify manifest.json contains correct metadata."""
        if not self.repo_path.is_dir():
            self.skipTest("Sample project fixture not found")

        self._ensure_db()

        from export_index_snapshot import run_export

        if not self.output_dir.is_dir():
            run_export(
                db_path=self.db_path,
                repo_id=self.repo_id,
                commit_sha=self.commit_sha,
                output_dir=self.output_dir,
            )

        manifest = json.loads(
            (self.output_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["repo_id"], self.repo_id)
        self.assertEqual(manifest["commit_sha"], self.commit_sha)
        self.assertIn("project_id", manifest)
        self.assertIn("file_count", manifest)
        self.assertIn("entity_count", manifest)
        self.assertIn("relation_count", manifest)
        self.assertGreater(manifest["file_count"], 0)
        self.assertGreater(manifest["entity_count"], 0)

    def test_export_frontend_diagnostics_structure(self):
        """Verify frontend_diagnostics.json has expected structure."""
        if not self.repo_path.is_dir():
            self.skipTest("Sample project fixture not found")

        self._ensure_db()

        from export_index_snapshot import run_export

        if not self.output_dir.is_dir():
            run_export(
                db_path=self.db_path,
                repo_id=self.repo_id,
                commit_sha=self.commit_sha,
                output_dir=self.output_dir,
            )

        data = json.loads(
            (self.output_dir / "frontend_diagnostics.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("identified_calls", data)
        self.assertIn("matched_calls", data)
        self.assertIn("unmatched_calls", data)
        self.assertIn("unresolved_candidates", data)
        self.assertIn("unmatched_examples", data)
        self.assertIn("unresolved_examples", data)
        # unmatched_calls should equal identified - matched.
        self.assertEqual(
            data["unmatched_calls"],
            data["identified_calls"] - data["matched_calls"],
        )


if __name__ == "__main__":
    unittest.main()
