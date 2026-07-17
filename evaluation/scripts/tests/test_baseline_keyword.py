#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for evaluation/runners/baseline_keyword.py.

Run with:
    backend\\.venv\\python.exe -m pytest evaluation/scripts/tests/test_baseline_keyword.py -v
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Make the runners directory importable.
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
# Helper to create a minimal evaluation dataset
# ---------------------------------------------------------------------------


def _make_dataset(
    questions: list[dict],
    path: Path,
) -> None:
    """Write a JSON-array dataset file."""
    path.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_SAMPLE_QUESTIONS = [
    {
        "question_id": "sample-retrieval-0001",
        "question": "Where is the alert list API implemented?",
        "evaluation_layers": ["retrieval"],
        "task_type": "CODE_QA",
        "language": "en",
    },
    {
        "question_id": "sample-retrieval-0002",
        "question": "AlertService findById",
        "evaluation_layers": ["retrieval"],
        "task_type": "CODE_QA",
        "language": "en",
    },
    {
        "question_id": "sample-trace-0001",
        "question": "Trace the alert call chain",
        "evaluation_layers": ["trace_chain"],
        "task_type": "TRACE_CHAIN",
        "language": "en",
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBaselineKeywordImport(unittest.TestCase):
    """Test that the script can be imported and its parser works."""

    def test_import_succeeds(self):
        import baseline_keyword  # noqa: F401

    def test_build_parser_help(self):
        from baseline_keyword import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_build_parser_required_args(self):
        from baseline_keyword import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "--repo",
                "/tmp/repo",
                "--dataset",
                "/tmp/dataset.json",
                "--db",
                "/tmp/test.db",
                "--output",
                "/tmp/output.jsonl",
                "--dataset-sha",
                "a" * 64,
                "--repo-commit",
                "b" * 40,
            ]
        )
        self.assertEqual(args.repo, Path("/tmp/repo"))
        self.assertEqual(args.dataset, Path("/tmp/dataset.json"))
        self.assertEqual(args.db, Path("/tmp/test.db"))
        self.assertEqual(args.output, Path("/tmp/output.jsonl"))
        self.assertEqual(args.top_k, 10)


class TestBaselineKeywordFilter(unittest.TestCase):
    """Test the dataset filtering logic."""

    def test_filter_retrieval_questions(self):
        from baseline_keyword import filter_retrieval_questions

        filtered = filter_retrieval_questions(_SAMPLE_QUESTIONS)
        self.assertEqual(len(filtered), 2)
        ids = {q["question_id"] for q in filtered}
        self.assertEqual(ids, {"sample-retrieval-0001", "sample-retrieval-0002"})

    def test_load_dataset_json(self):
        from baseline_keyword import load_dataset

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            encoding="utf-8",
            delete=False,
        ) as f:
            json.dump(_SAMPLE_QUESTIONS, f, ensure_ascii=False)
            f.flush()
            dataset = load_dataset(Path(f.name))
        os.unlink(f.name)
        self.assertEqual(len(dataset), 3)


class TestBaselineKeywordEndToEnd(unittest.TestCase):
    """End-to-end test using the sample_project fixture.

    This test actually scans the fixture and runs keyword search.
    It requires the backend virtualenv's Python and dependencies.
    """

    @classmethod
    def setUpClass(cls):
        cls.repo_path = Path(_FIXTURES_DIR)

    def _run_in_tmpdir(self, questions, top_k=10):
        """Run the baseline in a fresh temporary directory."""
        tmpdir = tempfile.mkdtemp()
        db_path = Path(tmpdir) / "test_baseline.db"
        output_path = Path(tmpdir) / "results.jsonl"
        dataset_path = Path(tmpdir) / "dataset.json"

        _make_dataset(questions, dataset_path)

        from baseline_keyword import run_baseline

        import subprocess
        commit = subprocess.run(
            ["git", "-C", str(self.repo_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        dataset_sha = hashlib.sha256(dataset_path.read_bytes()).hexdigest()

        run_baseline(
            repo=self.repo_path,
            dataset_path=dataset_path,
            db_path=db_path,
            output_path=output_path,
            top_k=top_k,
            dataset_sha256=dataset_sha,
            repo_commit=commit,
            metadata_path=Path(tmpdir) / "results.metadata.json",
        )
        return tmpdir, output_path

    def test_run_baseline_produces_output(self):
        """Run the full baseline and verify JSONL output."""
        if not self.repo_path.is_dir():
            self.skipTest(
                f"Sample project fixture not found: {self.repo_path}"
            )

        tmpdir, output_path = self._run_in_tmpdir(_SAMPLE_QUESTIONS)
        try:
            # Verify the output file exists and contains records.
            self.assertTrue(output_path.is_file())
            lines = output_path.read_text(encoding="utf-8").strip().splitlines()
            # Only retrieval-layer questions should appear (2 out of 3).
            self.assertEqual(len(lines), 2)

            for line in lines:
                record = json.loads(line)
                self.assertIn("question_id", record)
                self.assertIn("query", record)
                self.assertIn("hits", record)
                self.assertIn("total_hits", record)
                self.assertIn("execution_time_seconds", record)
                self.assertIn("scan_time_seconds", record)
                self.assertIn("entity_count", record)
                self.assertIn("project_id", record)
                self.assertEqual(record["variant"], "B1")
                self.assertEqual(record["run_index"], 0)
                for field in ("dataset_sha256", "repo_commit", "config_fingerprint", "run_id"):
                    self.assertTrue(record[field])
                # Entity count should be > 0 for the sample project.
                self.assertGreater(record["entity_count"], 0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_keyword_search_finds_alert_entities(self):
        """Verify that searching for 'alert' finds entities."""
        if not self.repo_path.is_dir():
            self.skipTest(
                f"Sample project fixture not found: {self.repo_path}"
            )

        # Use a single-word query that will match the casefolded content.
        alert_questions = [
            {
                "question_id": "sample-retrieval-0002",
                "question": "alert",
                "evaluation_layers": ["retrieval"],
                "task_type": "CODE_QA",
                "language": "en",
            },
        ]
        tmpdir, output_path = self._run_in_tmpdir(alert_questions)
        try:
            lines = output_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            # Should have at least one hit.
            self.assertGreater(
                len(record["hits"]),
                0,
                "Expected at least one hit for 'alert' query",
            )
            # Verify hit structure.
            hit = record["hits"][0]
            self.assertIn("entity_type", hit)
            self.assertIn("file_path", hit)
            self.assertIn("score", hit)
            self.assertIn("source", hit)
            self.assertEqual(hit["source"], "keyword")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestBaselineKeywordMainExit(unittest.TestCase):
    """Test the main() function's exit behavior."""

    def test_main_invalid_repo(self):
        from baseline_keyword import main

        result = main(
            [
                "--repo",
                "/nonexistent/path",
                "--dataset",
                "/tmp/dataset.json",
                "--db",
                "/tmp/test.db",
                "--output",
                "/tmp/output.jsonl",
                "--dataset-sha",
                "a" * 64,
                "--repo-commit",
                "b" * 40,
            ]
        )
        self.assertEqual(result, 1)

    def test_cli_requires_dataset_sha_and_repo_commit(self):
        from baseline_keyword import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "--repo", "/tmp/repo", "--dataset", "/tmp/dataset.json",
                "--db", "/tmp/test.db", "--output", "/tmp/output.jsonl",
            ])

    def test_main_invalid_dataset(self):
        from baseline_keyword import main

        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(
                [
                    "--repo",
                    tmpdir,
                    "--dataset",
                    "/nonexistent/dataset.json",
                    "--db",
                    os.path.join(tmpdir, "test.db"),
                    "--output",
                    os.path.join(tmpdir, "output.jsonl"),
                    "--dataset-sha",
                    "a" * 64,
                    "--repo-commit",
                    "b" * 40,
                ]
            )
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
