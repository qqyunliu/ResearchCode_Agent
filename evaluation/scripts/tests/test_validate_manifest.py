#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for validate_manifest.py.

Run with:
    python -m pytest tests/test_validate_manifest.py -v

Or from the project root:
    backend\\.venv\\python.exe -m pytest evaluation/scripts/tests/test_validate_manifest.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

# Ensure the scripts directory is importable.
_SCRIPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from validate_manifest import validate_manifest, _load_yaml_with_fallback

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_valid_entry(**overrides) -> dict:
    """Return a minimal valid repository entry dict."""
    entry = {
        "repo_id": "test-repo",
        "name": "Test Repo",
        "clone_url": "https://github.com/example/repo",
        "repository_subdir": "",
        "license": "MIT",
        "default_branch": "main",
        "commit_sha": "a" * 40,
        "primary_language": "python",
        "secondary_languages": [],
        "framework": "FastAPI",
        "file_counts_verified": True,
        "status": "cloned",
        "verified": True,
        "exclusion_reason": None,
        "notes": "Test repo.",
    }
    entry.update(overrides)
    return entry


def _minimal_manifest(**overrides) -> dict:
    """Return a minimal valid manifest dict."""
    repos = overrides.pop("repositories", None)
    manifest = {"version": "1.1"}
    manifest["repositories"] = repos if repos is not None else [_minimal_valid_entry()]
    manifest.update(overrides)
    return manifest


def _write_temp_manifest(content: str) -> str:
    """Write YAML content to a temp file, return its path."""
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="manifest_test_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# Tests: validate_manifest logic
# ---------------------------------------------------------------------------

class TestValidManifest(unittest.TestCase):
    """A fully valid manifest should produce zero errors."""

    def test_valid_manifest_passes(self):
        data = _minimal_manifest()
        errors = validate_manifest(data)
        self.assertEqual(errors, [], msg=f"Unexpected errors: {errors}")

    def test_valid_candidate_passes(self):
        entry = _minimal_valid_entry(
            status="candidate",
            commit_sha=None,
            verified=False,
            file_counts_verified=False,
        )
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertEqual(errors, [], msg=f"Unexpected errors: {errors}")

    def test_valid_indexed_passes(self):
        entry = _minimal_valid_entry(status="indexed")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertEqual(errors, [], msg=f"Unexpected errors: {errors}")


class TestDuplicateRepoId(unittest.TestCase):
    """Rule 1: repo_id must be unique."""

    def test_duplicate_repo_id_fails(self):
        entry1 = _minimal_valid_entry(repo_id="dup-repo")
        entry2 = _minimal_valid_entry(repo_id="dup-repo")
        data = _minimal_manifest(repositories=[entry1, entry2])
        errors = validate_manifest(data)
        self.assertTrue(any("duplicate" in e.reason.lower() for e in errors))

    def test_unique_repo_ids_pass(self):
        entry1 = _minimal_valid_entry(repo_id="repo-a")
        entry2 = _minimal_valid_entry(repo_id="repo-b")
        data = _minimal_manifest(repositories=[entry1, entry2])
        errors = validate_manifest(data)
        dup_errors = [e for e in errors if "duplicate" in e.reason.lower()]
        self.assertEqual(dup_errors, [])


class TestCommitShaFormat(unittest.TestCase):
    """Rule 3: commit_sha must be 40 hex chars when not null."""

    def test_valid_sha_passes(self):
        entry = _minimal_valid_entry(commit_sha="abcdef1234567890abcdef1234567890abcdef12")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        sha_errors = [e for e in errors if e.field == "commit_sha"]
        self.assertEqual(sha_errors, [])

    def test_null_sha_allowed_for_candidate(self):
        entry = _minimal_valid_entry(status="candidate", commit_sha=None)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        sha_errors = [e for e in errors if e.field == "commit_sha"]
        self.assertEqual(sha_errors, [])

    def test_short_sha_fails(self):
        entry = _minimal_valid_entry(commit_sha="abc123", status="cloned")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(any(e.field == "commit_sha" for e in errors))

    def test_uppercase_sha_fails(self):
        entry = _minimal_valid_entry(commit_sha="A" * 40, status="cloned")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(any(e.field == "commit_sha" for e in errors))

    def test_non_hex_sha_fails(self):
        entry = _minimal_valid_entry(commit_sha="g" * 40, status="cloned")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(any(e.field == "commit_sha" for e in errors))


class TestClonedWithoutCommitSha(unittest.TestCase):
    """Rule 5: cloned/indexed repos must have a non-null commit_sha."""

    def test_cloned_without_sha_fails(self):
        entry = _minimal_valid_entry(status="cloned", commit_sha=None)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "commit_sha" and "null" in e.reason.lower() for e in errors),
            msg=f"Expected commit_sha null error, got: {errors}",
        )

    def test_indexed_without_sha_fails(self):
        entry = _minimal_valid_entry(status="indexed", commit_sha=None)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "commit_sha" and "null" in e.reason.lower() for e in errors),
        )

    def test_cloned_with_sha_passes(self):
        entry = _minimal_valid_entry(status="cloned", commit_sha="b" * 40)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        sha_null_errors = [e for e in errors if e.field == "commit_sha" and "null" in e.reason.lower()]
        self.assertEqual(sha_null_errors, [])


class TestSubdirectoryUrl(unittest.TestCase):
    """Rule 2: clone_url must not be a subdirectory URL."""

    def test_subdirectory_url_fails(self):
        entry = _minimal_valid_entry(
            clone_url="https://github.com/org/repo/tree/main/subdir"
        )
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "clone_url" and "subdirectory" in e.reason.lower() for e in errors),
            msg=f"Expected subdirectory URL error, got: {errors}",
        )

    def test_blob_url_fails(self):
        entry = _minimal_valid_entry(
            clone_url="https://github.com/org/repo/blob/main/file.py"
        )
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "clone_url" and "subdirectory" in e.reason.lower() for e in errors),
        )

    def test_valid_clone_url_passes(self):
        entry = _minimal_valid_entry(clone_url="https://github.com/org/repo")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        url_errors = [e for e in errors if e.field == "clone_url"]
        self.assertEqual(url_errors, [])

    def test_null_clone_url_for_fixture_passes(self):
        """Fixture entries (clone_url=null) are allowed."""
        entry = _minimal_valid_entry(
            repo_id="sample-project",
            clone_url=None,
            parent_repo="ResearchCode-Agent",
            status="selected",
            verified=True,
            file_counts_verified=True,
            license=None,
        )
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        url_errors = [e for e in errors if e.field == "clone_url"]
        self.assertEqual(url_errors, [])


class TestGplLicenseNote(unittest.TestCase):
    """Rule 8: GPL entries must have a license_note."""

    def test_gpl_without_license_note_fails(self):
        entry = _minimal_valid_entry(license="GPL-3.0", license_note=None)
        # Remove license_note entirely
        del entry["license_note"]
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "license_note" for e in errors),
            msg=f"Expected license_note error, got: {errors}",
        )

    def test_gpl_with_license_note_passes(self):
        entry = _minimal_valid_entry(
            license="GPL-3.0",
            license_note="GPL-3.0 boundary candidate only",
        )
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        ln_errors = [e for e in errors if e.field == "license_note"]
        self.assertEqual(ln_errors, [])

    def test_mit_without_license_note_passes(self):
        """Non-GPL licenses don't require a license_note."""
        entry = _minimal_valid_entry(license="MIT")
        if "license_note" in entry:
            del entry["license_note"]
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        ln_errors = [e for e in errors if e.field == "license_note"]
        self.assertEqual(ln_errors, [])


class TestVerifiedRequiresFileCountsVerified(unittest.TestCase):
    """Rule 6: verified=true requires file_counts_verified=true."""

    def test_verified_without_file_counts_verified_fails(self):
        entry = _minimal_valid_entry(verified=True, file_counts_verified=False)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "file_counts_verified" for e in errors),
            msg=f"Expected file_counts_verified error, got: {errors}",
        )

    def test_verified_with_file_counts_verified_passes(self):
        entry = _minimal_valid_entry(verified=True, file_counts_verified=True)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        fc_errors = [e for e in errors if e.field == "file_counts_verified"]
        self.assertEqual(fc_errors, [])

    def test_not_verified_with_false_file_counts_passes(self):
        entry = _minimal_valid_entry(verified=False, file_counts_verified=False)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        fc_errors = [e for e in errors if e.field == "file_counts_verified"]
        self.assertEqual(fc_errors, [])


class TestRepositorySubdir(unittest.TestCase):
    """Rule 9: repository_subdir must be a string."""

    def test_empty_string_passes(self):
        entry = _minimal_valid_entry(repository_subdir="")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        sd_errors = [e for e in errors if e.field == "repository_subdir"]
        self.assertEqual(sd_errors, [])

    def test_nonempty_string_passes(self):
        entry = _minimal_valid_entry(repository_subdir="apps/python-fastapi")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        sd_errors = [e for e in errors if e.field == "repository_subdir"]
        self.assertEqual(sd_errors, [])

    def test_integer_subdir_fails(self):
        entry = _minimal_valid_entry(repository_subdir=123)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(any(e.field == "repository_subdir" for e in errors))


class TestSampleProjectParentRepo(unittest.TestCase):
    """Rule 10: sample-project must have parent_repo."""

    def test_sample_project_with_parent_repo_passes(self):
        entry = _minimal_valid_entry(
            repo_id="sample-project",
            clone_url=None,
            license=None,
            parent_repo="ResearchCode-Agent",
            verified=True,
            file_counts_verified=True,
        )
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        pr_errors = [e for e in errors if e.field == "parent_repo"]
        self.assertEqual(pr_errors, [])

    def test_sample_project_without_parent_repo_fails(self):
        entry = _minimal_valid_entry(
            repo_id="sample-project",
            clone_url=None,
            license=None,
            verified=True,
            file_counts_verified=True,
        )
        # Ensure parent_repo is not set
        entry.pop("parent_repo", None)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "parent_repo" for e in errors),
            msg=f"Expected parent_repo error, got: {errors}",
        )


class TestStatusValues(unittest.TestCase):
    """Rule 4: status must be a valid value."""

    def test_invalid_status_fails(self):
        entry = _minimal_valid_entry(status="unknown")
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(any(e.field == "status" for e in errors))

    def test_all_valid_statuses_pass(self):
        for status in ["candidate", "selected", "cloned", "indexed"]:
            entry = _minimal_valid_entry(
                status=status,
                commit_sha="a" * 40 if status in ("cloned", "indexed") else None,
            )
            data = _minimal_manifest(repositories=[entry])
            errors = validate_manifest(data)
            status_errors = [e for e in errors if e.field == "status"]
            self.assertEqual(status_errors, [], msg=f"Status '{status}' should be valid, got: {status_errors}")


class TestLicenseForNonFixture(unittest.TestCase):
    """Rule 7: non-fixture entries must have a license."""

    def test_non_fixture_without_license_fails(self):
        entry = _minimal_valid_entry(license=None)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        self.assertTrue(
            any(e.field == "license" for e in errors),
            msg=f"Expected license error, got: {errors}",
        )

    def test_fixture_without_license_passes(self):
        entry = _minimal_valid_entry(
            repo_id="sample-project",
            clone_url=None,
            license=None,
            parent_repo="ResearchCode-Agent",
            verified=True,
            file_counts_verified=True,
        )
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data)
        license_errors = [e for e in errors if e.field == "license"]
        self.assertEqual(license_errors, [])


class TestCLIInterface(unittest.TestCase):
    """Test the CLI interface via subprocess."""

    @classmethod
    def setUpClass(cls):
        cls.python = sys.executable
        cls.script = os.path.join(_SCRIPTS_DIR, "validate_manifest.py")

    def test_help_flag(self):
        result = subprocess.run(
            [self.python, self.script, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("manifest", result.stdout.lower())

    def test_valid_manifest_returns_zero(self):
        """Write a valid manifest to a temp file and validate it."""
        valid_yaml = textwrap.dedent("""\
            version: "1.1"
            repositories:
              - repo_id: test-repo
                name: "Test Repo"
                clone_url: "https://github.com/example/repo"
                repository_subdir: ""
                license: "MIT"
                default_branch: "main"
                commit_sha: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                primary_language: "python"
                secondary_languages: []
                framework: "FastAPI"
                file_counts_verified: true
                status: cloned
                verified: true
                exclusion_reason: null
                notes: "Test."
        """)
        path = _write_temp_manifest(valid_yaml)
        try:
            result = subprocess.run(
                [self.python, self.script, "--manifest", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("OK", result.stdout)
        finally:
            os.unlink(path)

    def test_invalid_manifest_returns_one(self):
        """Write an invalid manifest (duplicate repo_id) and validate it."""
        invalid_yaml = textwrap.dedent("""\
            version: "1.1"
            repositories:
              - repo_id: dup-repo
                name: "Repo 1"
                clone_url: "https://github.com/example/repo1"
                repository_subdir: ""
                license: "MIT"
                default_branch: "main"
                commit_sha: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                primary_language: "python"
                secondary_languages: []
                framework: "FastAPI"
                file_counts_verified: true
                status: cloned
                verified: true
                exclusion_reason: null
                notes: "First."
              - repo_id: dup-repo
                name: "Repo 2"
                clone_url: "https://github.com/example/repo2"
                repository_subdir: ""
                license: "Apache-2.0"
                default_branch: "main"
                commit_sha: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                primary_language: "java"
                secondary_languages: []
                framework: "Spring Boot"
                file_counts_verified: true
                status: cloned
                verified: true
                exclusion_reason: null
                notes: "Second."
        """)
        path = _write_temp_manifest(invalid_yaml)
        try:
            result = subprocess.run(
                [self.python, self.script, "--manifest", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 1, msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("FAIL", result.stdout)
        finally:
            os.unlink(path)

    def test_missing_file_returns_two(self):
        result = subprocess.run(
            [self.python, self.script, "--manifest", "/nonexistent/manifest.yaml"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 2, msg=result.stderr)


class TestCheckWorkspaces(unittest.TestCase):
    """Rule 11: optional workspace existence check."""

    def test_cloned_repo_missing_workspace_fails(self):
        entry = _minimal_valid_entry(status="cloned", commit_sha="c" * 40)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data, check_workspaces=True, workspace_root="/tmp/nonexistent_workspaces")
        self.assertTrue(
            any(e.field == "workspace" for e in errors),
            msg=f"Expected workspace error, got: {errors}",
        )

    def test_cloned_repo_with_existing_workspace_passes(self):
        import tempfile as _tf
        with _tf.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "test-repo")
            os.makedirs(repo_dir)
            entry = _minimal_valid_entry(status="cloned", commit_sha="c" * 40)
            data = _minimal_manifest(repositories=[entry])
            errors = validate_manifest(data, check_workspaces=True, workspace_root=tmpdir)
            ws_errors = [e for e in errors if e.field == "workspace"]
            self.assertEqual(ws_errors, [])

    def test_candidate_repo_skips_workspace_check(self):
        """Candidates are not cloned, so no workspace check."""
        entry = _minimal_valid_entry(status="candidate", commit_sha=None, verified=False, file_counts_verified=False)
        data = _minimal_manifest(repositories=[entry])
        errors = validate_manifest(data, check_workspaces=True, workspace_root="/nonexistent")
        ws_errors = [e for e in errors if e.field == "workspace"]
        self.assertEqual(ws_errors, [])


if __name__ == "__main__":
    unittest.main()
