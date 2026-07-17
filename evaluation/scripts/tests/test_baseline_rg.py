#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for evaluation/runners/baseline_rg.py.

Run with:
    backend\\.venv\\python.exe -m pytest evaluation/scripts/tests/test_baseline_rg.py -v
"""

from __future__ import annotations

import json
import hashlib
import os
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

from baseline_rg import (
    build_parser,
    extract_tokens,
    filter_retrieval_questions,
    load_dataset,
    search_repo,
    run_baseline,
)


# ---------------------------------------------------------------------------
# Token extraction tests
# ---------------------------------------------------------------------------


class TestExtractTokens(unittest.TestCase):
    """Tests for the extract_tokens function."""

    def test_english_query(self):
        tokens = extract_tokens("Where is the alert list API implemented?")
        self.assertIn("where", tokens)
        self.assertIn("alert", tokens)
        self.assertIn("list", tokens)
        self.assertIn("implemented", tokens)
        # Short words like "is" are filtered out (< 3 chars).
        self.assertNotIn("is", tokens)
        # "the" and "api" are exactly 3 chars, so they pass the filter.
        self.assertIn("the", tokens)
        self.assertIn("api", tokens)

    def test_chinese_query(self):
        tokens = extract_tokens("告警列表接口在哪里实现的")
        # Chinese characters are individual tokens; only those >= 3 chars survive.
        # Since each CJK char is 1 char, none will pass the min_length=3 filter
        # unless there are multi-char sequences.
        # In this case, the tokenizer splits on punctuation and whitespace.
        # The whole string is one token "告警列表接口在哪里实现的" which is 11 chars.
        self.assertTrue(len(tokens) >= 1)

    def test_short_tokens_filtered(self):
        tokens = extract_tokens("ab cd ef ghij")
        self.assertEqual(tokens, ["ghij"])

    def test_punctuation_split(self):
        tokens = extract_tokens("AlertService.findById()")
        self.assertIn("alertservice", tokens)
        self.assertIn("findbyid", tokens)

    def test_empty_query(self):
        tokens = extract_tokens("")
        self.assertEqual(tokens, [])

    def test_all_short_tokens(self):
        tokens = extract_tokens("a b cc")
        self.assertEqual(tokens, [])

    def test_min_length_custom(self):
        tokens = extract_tokens("ab cde fghij", min_length=2)
        self.assertIn("ab", tokens)
        self.assertIn("cde", tokens)
        self.assertIn("fghij", tokens)

    def test_api_path_query(self):
        tokens = extract_tokens("/api/alerts/search")
        self.assertIn("api", tokens)
        self.assertIn("alerts", tokens)
        self.assertIn("search", tokens)


# ---------------------------------------------------------------------------
# Dataset loading tests
# ---------------------------------------------------------------------------


class TestLoadDataset(unittest.TestCase):
    """Tests for load_dataset and filter_retrieval_questions."""

    def test_load_json_array(self):
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            encoding="utf-8",
            delete=False,
        ) as f:
            json.dump(
                [
                    {
                        "question_id": "test-0001",
                        "question": "Where is the alert API?",
                        "evaluation_layers": ["retrieval"],
                    }
                ],
                f,
                ensure_ascii=False,
            )
            f.flush()
            dataset = load_dataset(Path(f.name))
        os.unlink(f.name)
        self.assertEqual(len(dataset), 1)
        self.assertEqual(dataset[0]["question_id"], "test-0001")

    def test_load_jsonl(self):
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".jsonl",
            encoding="utf-8",
            delete=False,
        ) as f:
            f.write(
                json.dumps(
                    {
                        "question_id": "test-0001",
                        "question": "Where is the alert API?",
                        "evaluation_layers": ["retrieval"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "question_id": "test-0002",
                        "question": "How does tracing work?",
                        "evaluation_layers": ["trace_chain"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.flush()
            dataset = load_dataset(Path(f.name))
        os.unlink(f.name)
        self.assertEqual(len(dataset), 2)

    def test_filter_retrieval_questions(self):
        dataset = [
            {
                "question_id": "q1",
                "question": "alert",
                "evaluation_layers": ["retrieval"],
            },
            {
                "question_id": "q2",
                "question": "trace",
                "evaluation_layers": ["trace_chain"],
            },
            {
                "question_id": "q3",
                "question": "both",
                "evaluation_layers": ["retrieval", "trace_chain"],
            },
        ]
        filtered = filter_retrieval_questions(dataset)
        self.assertEqual(len(filtered), 2)
        ids = {q["question_id"] for q in filtered}
        self.assertEqual(ids, {"q1", "q3"})

    def test_filter_empty_layers(self):
        dataset = [
            {"question_id": "q1", "question": "test", "evaluation_layers": []},
        ]
        filtered = filter_retrieval_questions(dataset)
        self.assertEqual(len(filtered), 0)


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


class TestSearchRepo(unittest.TestCase):
    """Tests for search_repo with a temporary repository."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create a simple repository structure.
        src_dir = Path(self.tmpdir) / "src"
        src_dir.mkdir()
        (src_dir / "AlertService.java").write_text(
            "class AlertService {\n"
            "    Alert findById(Long id) {\n"
            "        return null;\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        (src_dir / "AlertController.java").write_text(
            "@RestController\n"
            "@RequestMapping(\"/api/alerts\")\n"
            "class AlertController {\n"
            "    AlertService alertService;\n"
            "}\n",
            encoding="utf-8",
        )
        (src_dir / "UserService.java").write_text(
            "class UserService {\n"
            "    User findUser(Long id) {\n"
            "        return null;\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_search_finds_matching_files(self):
        hits = search_repo(Path(self.tmpdir), ["alertservice"])
        self.assertTrue(len(hits) > 0)
        file_paths = [h["file_path"] for h in hits]
        # AlertService.java should match.
        self.assertTrue(
            any("AlertService" in fp for fp in file_paths),
            f"Expected AlertService in hits: {file_paths}",
        )

    def test_search_ranks_by_match_count(self):
        # "alertservice" appears in both AlertService.java and AlertController.java
        # but AlertService.java has more occurrences.
        hits = search_repo(Path(self.tmpdir), ["alert", "service"])
        self.assertTrue(len(hits) >= 2)
        # The first hit should have the highest score.
        self.assertGreaterEqual(hits[0]["score"], hits[-1]["score"])

    def test_search_empty_tokens(self):
        hits = search_repo(Path(self.tmpdir), [])
        self.assertEqual(hits, [])

    def test_search_no_matches(self):
        hits = search_repo(Path(self.tmpdir), ["nonexistenttoken"])
        self.assertEqual(hits, [])

    def test_search_score_calculation(self):
        hits = search_repo(Path(self.tmpdir), ["alertservice", "findbyid"])
        for hit in hits:
            self.assertIn("file_path", hit)
            self.assertIn("match_count", hit)
            self.assertIn("score", hit)
            self.assertIn("token_counts", hit)
            # Score should be between 0 and 1.
            self.assertGreaterEqual(hit["score"], 0.0)
            self.assertLessEqual(hit["score"], 1.0)


# ---------------------------------------------------------------------------
# CLI parser tests
# ---------------------------------------------------------------------------


class TestBuildParser(unittest.TestCase):
    """Tests for the CLI argument parser."""

    def test_help_flag(self):
        parser = build_parser()
        # Parsing --help should raise SystemExit with code 0.
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_required_args(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--repo",
                "/tmp/repo",
                "--dataset",
                "/tmp/dataset.json",
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
        self.assertEqual(args.output, Path("/tmp/output.jsonl"))
        self.assertEqual(args.top_k, 10)

    def test_top_k_custom(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--repo",
                "/tmp/repo",
                "--dataset",
                "/tmp/dataset.json",
                "--output",
                "/tmp/output.jsonl",
                "--top-k",
                "20",
                "--dataset-sha",
                "a" * 64,
                "--repo-commit",
                "b" * 40,
            ]
        )
        self.assertEqual(args.top_k, 20)

    def test_missing_required_args(self):
        parser = build_parser()
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--repo", "/tmp/repo"])
        self.assertNotEqual(ctx.exception.code, 0)


class TestStage2BIdentityContract(unittest.TestCase):
    def test_run_writes_complete_identity_and_completed_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "repo"
            repo.mkdir()
            (repo / "Example.java").write_text("class Example {}", encoding="utf-8")
            subprocess_args = ["git", "init", "-q", str(repo)]
            import subprocess
            subprocess.run(subprocess_args, check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "Example.java"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
            commit = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            dataset = root / "dataset.jsonl"
            dataset.write_text(json.dumps({
                "question_id": "q1", "question": "Example",
                "evaluation_layers": ["retrieval"],
            }) + "\n", encoding="utf-8")
            dataset_sha = hashlib.sha256(dataset.read_bytes()).hexdigest()
            output = root / "b0.jsonl"
            metadata = root / "b0.metadata.json"

            run_baseline(repo, dataset, output, 10, dataset_sha256=dataset_sha,
                         repo_commit=commit, metadata_path=metadata)

            record = json.loads(output.read_text(encoding="utf-8"))
            identity_fields = {"dataset_sha256", "repo_commit", "config_fingerprint", "run_id", "variant", "run_index"}
            self.assertTrue(identity_fields <= record.keys())
            self.assertEqual(record["variant"], "B0")
            self.assertEqual(record["run_index"], 0)
            sidecar = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(sidecar["status"], "completed")
            self.assertEqual(sidecar["records_written"], 1)
            for field in identity_fields - {"variant", "run_index"}:
                self.assertEqual(sidecar[field], record[field])

    def test_cli_requires_dataset_sha_and_repo_commit(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "--repo", "/tmp/repo", "--dataset", "/tmp/dataset.json",
                "--output", "/tmp/output.jsonl",
            ])


if __name__ == "__main__":
    unittest.main()
