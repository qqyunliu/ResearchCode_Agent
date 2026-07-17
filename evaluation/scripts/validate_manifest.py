#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate evaluation/repos/manifest.yaml against the evaluation SPEC rules.

This script checks the repository manifest for structural and semantic
correctness **without** modifying any product code. It is designed to run
in CI or locally before evaluation stages begin.

Validation rules (aligned with SPEC.md Section 4 and the manifest header):

 1. ``repo_id`` must be unique across all entries.
 2. ``clone_url`` must not be null for non-fixture entries and must not
    be a subdirectory URL (e.g. ``.../tree/main/subdir``).
 3. ``commit_sha``, when not null, must be exactly 40 lowercase hex characters.
 4. ``status`` must be one of: candidate, selected, cloned, indexed.
 5. Entries with ``status: cloned`` (or ``indexed``) must have a non-null
    ``commit_sha``.
 6. Entries with ``verified: true`` must also have
    ``file_counts_verified: true``.
 7. ``license`` must exist (not null) for non-fixture entries.
 8. GPL-licensed entries must include a ``license_note``.
 9. ``repository_subdir`` must be a string (may be empty).
10. ``sample-project`` (the internal fixture) must have a ``parent_repo``
    field.
11. (Optional) For cloned repos, the local workspace directory must exist.

Usage::

    python validate_manifest.py
    python validate_manifest.py --manifest path/to/manifest.yaml
    python validate_manifest.py --check-workspaces

Exit code 0 = all checks passed, 1 = one or more validation errors found.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# YAML loading with PyYAML fallback
# ---------------------------------------------------------------------------

try:
    import yaml  # type: ignore[import-untyped]

    _HAS_PYYAML = True
except ImportError:
    _HAS_PYYAML = False


def _load_yaml_with_fallback(path: str) -> Dict[str, Any]:
    """Load the manifest YAML.

    Prefers PyYAML when available. Falls back to a purpose-built simple
    parser that handles the specific structure of the evaluation manifest.
    The fallback is intentionally limited -- it handles flat key-value
    pairs and lists of mappings (the manifest's structure) but not
    arbitrary YAML.
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    if _HAS_PYYAML:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise ValueError(
                f"Manifest root must be a YAML mapping, got {type(data).__name__}"
            )
        return data

    # --- Minimal fallback parser for the manifest structure ---
    # This handles the specific shape of evaluation/repos/manifest.yaml:
    #   version: "1.1"
    #   repositories:
    #     - key: value
    #       key: value
    #       ...
    #
    # Limitations: no anchors, no multi-line strings, no flow mappings.
    return _simple_manifest_parser(raw)


def _simple_manifest_parser(raw: str) -> Dict[str, Any]:
    """Minimal parser for the evaluation manifest YAML structure.

    Handles top-level scalars and a single ``repositories`` list of
    flat mappings. Not a general-purpose YAML parser.
    """
    result: Dict[str, Any] = {}
    repos: List[Dict[str, Any]] = []
    current_entry: Optional[Dict[str, Any]] = None
    in_repos = False

    for raw_line in raw.splitlines():
        # Strip comments (but not inside quoted strings -- good enough here).
        line = raw_line.split("  #")[0].rstrip()
        stripped = line.lstrip()

        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(stripped)

        if indent == 0:
            # Top-level key
            in_repos = False
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "repositories":
                    in_repos = True
                    continue
                result[key] = _parse_scalar(val)
            continue

        if in_repos:
            if stripped.startswith("- "):
                # New list item
                if current_entry is not None:
                    repos.append(current_entry)
                current_entry = {}
                # The first key-value on the "- " line
                kv = stripped[2:]
                if ":" in kv:
                    k, _, v = kv.partition(":")
                    current_entry[k.strip()] = _parse_scalar(v.strip())
            elif ":" in stripped and current_entry is not None:
                k, _, v = stripped.partition(":")
                k = k.strip()
                v = v.strip()
                # Handle inline list like ["vue", "javascript"]
                if v.startswith("["):
                    current_entry[k] = _parse_inline_list(v)
                else:
                    current_entry[k] = _parse_scalar(v)

    if current_entry is not None:
        repos.append(current_entry)

    result["repositories"] = repos
    return result


def _parse_scalar(val: str) -> Any:
    """Parse a YAML scalar value into a Python type."""
    if not val or val == "null" or val == "~":
        return None
    if val == "true":
        return True
    if val == "false":
        return False
    # Quoted string
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        return val[1:-1]
    # Try int
    try:
        return int(val)
    except ValueError:
        pass
    # Try float
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _parse_inline_list(val: str) -> list:
    """Parse a YAML inline list like ``["vue", "javascript"]``."""
    inner = val.strip("[] ")
    if not inner:
        return []
    items = []
    for part in inner.split(","):
        items.append(_parse_scalar(part.strip()))
    return items


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

# The valid status progression.
_VALID_STATUSES = ["candidate", "selected", "cloned", "indexed"]
_STATUS_ORDER = {s: i for i, s in enumerate(_VALID_STATUSES)}

# Regex for a valid 40-char lowercase hex SHA-1 (Git commit).
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Patterns that indicate a subdirectory URL rather than a repo root URL.
_SUBDIR_URL_PATTERNS = [
    re.compile(r"/tree/[^/]+/.+"),  # GitHub: /tree/branch/path
    re.compile(r"/blob/[^/]+/.+"),  # GitHub: /blob/branch/path
]


class ManifestError:
    """A single validation error with context for reporting."""

    __slots__ = ("repo_id", "field", "value", "reason")

    def __init__(
        self,
        repo_id: str,
        field: str,
        value: Any,
        reason: str,
    ):
        self.repo_id = repo_id
        self.field = field
        self.value = value
        self.reason = reason

    def __str__(self) -> str:
        val_repr = repr(self.value)
        if len(val_repr) > 80:
            val_repr = val_repr[:77] + "..."
        return (
            f"[{self.repo_id}] {self.field} = {val_repr} -- {self.reason}"
        )


def _is_fixture(entry: Dict[str, Any]) -> bool:
    """Return True if the entry is a local fixture (no real clone_url)."""
    return entry.get("clone_url") is None


def validate_manifest(
    data: Dict[str, Any],
    check_workspaces: bool = False,
    workspace_root: Optional[str] = None,
) -> List[ManifestError]:
    """Validate the parsed manifest data.

    Parameters
    ----------
    data : dict
        Parsed YAML manifest.
    check_workspaces : bool
        If True, verify that cloned repos have a local workspace directory.
    workspace_root : str, optional
        Root directory for workspaces. Defaults to
        ``evaluation/workspaces/`` relative to the manifest.

    Returns
    -------
    list of ManifestError
        Empty list means all checks passed.
    """
    errors: List[ManifestError] = []
    repos = data.get("repositories", [])

    if not isinstance(repos, list):
        errors.append(
            ManifestError(
                "(root)", "repositories", type(repos).__name__,
                "must be a YAML list",
            )
        )
        return errors

    # --- Rule 1: repo_id uniqueness ---
    seen_ids: Dict[str, int] = {}
    for idx, entry in enumerate(repos):
        rid = entry.get("repo_id", f"<missing-{idx}>")
        if rid in seen_ids:
            errors.append(
                ManifestError(
                    rid, "repo_id", rid,
                    f"duplicate repo_id (first seen at index {seen_ids[rid]})",
                )
            )
        else:
            seen_ids[rid] = idx

    # --- Per-entry checks ---
    for entry in repos:
        rid = entry.get("repo_id", "<unknown>")
        is_fixture = _is_fixture(entry)

        # Rule 2: clone_url validity for non-fixture entries
        clone_url = entry.get("clone_url")
        if not is_fixture:
            if clone_url is None:
                errors.append(
                    ManifestError(
                        rid, "clone_url", clone_url,
                        "must not be null for non-fixture entries",
                    )
                )
            elif isinstance(clone_url, str):
                for pat in _SUBDIR_URL_PATTERNS:
                    if pat.search(clone_url):
                        errors.append(
                            ManifestError(
                                rid, "clone_url", clone_url,
                                "must be a repository root URL, not a "
                                "subdirectory URL",
                            )
                        )
                        break

        # Rule 3: commit_sha format (when not null)
        commit_sha = entry.get("commit_sha")
        if commit_sha is not None:
            if not isinstance(commit_sha, str) or not _SHA_RE.match(commit_sha):
                errors.append(
                    ManifestError(
                        rid, "commit_sha", commit_sha,
                        "must be a 40-character lowercase hex string "
                        "(valid Git SHA)",
                    )
                )

        # Rule 4: status must be a valid value
        status = entry.get("status")
        if status not in _VALID_STATUSES:
            errors.append(
                ManifestError(
                    rid, "status", status,
                    f"must be one of {_VALID_STATUSES}",
                )
            )

        # Rule 5: cloned/indexed repos must have commit_sha
        if status in ("cloned", "indexed") and commit_sha is None:
            errors.append(
                ManifestError(
                    rid, "commit_sha", commit_sha,
                    f"must not be null when status is '{status}'",
                )
            )

        # Rule 6: verified=true => file_counts_verified=true
        verified = entry.get("verified")
        file_counts_verified = entry.get("file_counts_verified")
        if verified is True and file_counts_verified is not True:
            errors.append(
                ManifestError(
                    rid, "file_counts_verified", file_counts_verified,
                    "must be true when verified is true",
                )
            )

        # Rule 7: license must exist for non-fixture entries
        if not is_fixture:
            license_val = entry.get("license")
            if license_val is None:
                errors.append(
                    ManifestError(
                        rid, "license", license_val,
                        "must not be null for non-fixture entries",
                    )
                )

        # Rule 8: GPL entries must have license_note
        license_str = str(entry.get("license", "") or "")
        if "gpl" in license_str.lower():
            license_note = entry.get("license_note")
            if not license_note:
                errors.append(
                    ManifestError(
                        rid, "license_note", license_note,
                        "GPL-licensed entries must include a license_note "
                        "explaining the boundary-candidate status",
                    )
                )

        # Rule 9: repository_subdir must be a string (may be empty)
        subdir = entry.get("repository_subdir")
        if subdir is not None and not isinstance(subdir, str):
            errors.append(
                ManifestError(
                    rid, "repository_subdir", subdir,
                    "must be a string (may be empty)",
                )
            )

        # Rule 10: sample-project must have parent_repo
        if rid == "sample-project":
            parent_repo = entry.get("parent_repo")
            if not parent_repo:
                errors.append(
                    ManifestError(
                        rid, "parent_repo", parent_repo,
                        "the internal fixture must declare a parent_repo field",
                    )
                )

        # Rule 11 (optional): workspace directory exists for cloned repos
        if check_workspaces and status in ("cloned", "indexed"):
            ws_root = workspace_root or os.path.normpath(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    os.pardir,
                    "workspaces",
                )
            )
            ws_path = os.path.join(ws_root, rid)
            if not os.path.isdir(ws_path):
                errors.append(
                    ManifestError(
                        rid, "workspace", ws_path,
                        f"workspace directory does not exist (expected at "
                        f"{ws_path})",
                    )
                )

    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate evaluation/repos/manifest.yaml against the "
            "evaluation SPEC rules. Exit code 0 means all checks passed; "
            "exit code 1 means one or more validation errors were found."
        ),
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help=(
            "Path to the manifest YAML file. "
            "Default: evaluation/repos/manifest.yaml (relative to project root)."
        ),
    )
    parser.add_argument(
        "--check-workspaces",
        action="store_true",
        help=(
            "Also verify that local workspace directories exist for "
            "repos with status 'cloned' or 'indexed'."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help=(
            "Root directory for workspace checks. "
            "Default: evaluation/workspaces/ (relative to project root)."
        ),
    )
    return parser


def _resolve_default_manifest() -> str:
    """Return the default manifest path relative to the project root.

    The script lives at ``evaluation/scripts/validate_manifest.py``,
    so the project root is two levels up.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.normpath(os.path.join(script_dir, os.pardir, os.pardir))
    return os.path.join(project_root, "evaluation", "repos", "manifest.yaml")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns 0 on success, 1 on validation failure, 2 on usage errors.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    manifest_path = args.manifest or _resolve_default_manifest()

    if not os.path.isfile(manifest_path):
        print(f"Error: manifest file not found: {manifest_path}", file=sys.stderr)
        return 2

    try:
        data = _load_yaml_with_fallback(manifest_path)
    except Exception as exc:
        print(f"Error: failed to parse manifest: {exc}", file=sys.stderr)
        return 2

    errors = validate_manifest(
        data,
        check_workspaces=args.check_workspaces,
        workspace_root=args.workspace_root,
    )

    if errors:
        print(f"FAIL: {len(errors)} validation error(s) found:\n")
        for err in errors:
            print(f"  {err}")
        print(f"\nManifest: {manifest_path}")
        return 1
    else:
        repo_count = len(data.get("repositories", []))
        print(f"OK: manifest is valid ({repo_count} repositories checked)")
        print(f"Manifest: {manifest_path}")
        if not _HAS_PYYAML:
            print(
                "Note: PyYAML not installed; using limited fallback parser. "
                "Install PyYAML for full YAML support."
            )
        return 0


if __name__ == "__main__":
    sys.exit(main())
