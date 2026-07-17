#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Entity Key computation (SPEC.md Section 7.5).

Database auto-increment ``entity_id`` is NOT stable across rescans.
Gold labels use ``stable_entity_key``, defined as the SHA-256 of the
normalized concatenation::

    repo_id|commit_sha|relative_file_path|entity_type|qualified_name|start_line|end_line

Normalization rules:
  - File paths use POSIX separators (forward slashes).
  - File paths are lowercased.
  - Fields are joined with ``|`` (pipe character).
  - No trailing whitespace or newline before hashing.

Usage as CLI::

    python stable_entity_key.py \\
        --repo-id ruoyi-vue \\
        --commit-sha 41720e624c5a668c7d3777835e4c87095a7a1dfd \\
        --file-path ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java \\
        --entity-type class \\
        --qualified-name com.ruoyi.web.controller.system.SysUserController \\
        --start-line 15 \\
        --end-line 120

Usage as a library::

    from stable_entity_key import compute_stable_key, compute_stable_key_from_dict

    key = compute_stable_key(
        repo_id="ruoyi-vue",
        commit_sha="41720e624c5a668c7d3777835e4c87095a7a1dfd",
        file_path="ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        entity_type="class",
        qualified_name="com.ruoyi.web.controller.system.SysUserController",
        start_line=15,
        end_line=120,
    )
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import PurePosixPath
from typing import Any, Dict, Union


def _normalize_file_path(file_path: str) -> str:
    """Normalize a file path to POSIX separators and lowercase.

    Why: Windows paths use backslashes; gold labels must be
    platform-independent so the same entity hashes identically
    regardless of the OS that produced the scan.
    """
    # PurePosixPath handles forward-slash paths natively.
    # We first replace backslashes with forward slashes so that
    # Windows-style paths are correctly interpreted.
    posix = file_path.replace("\\", "/")
    # Lowercase for case-insensitive comparison (matches SPEC rule).
    return posix.lower()


def compute_stable_key(
    repo_id: str,
    commit_sha: str,
    file_path: str,
    entity_type: str,
    qualified_name: str,
    start_line: Union[int, str],
    end_line: Union[int, str],
) -> str:
    """Compute the SHA-256 stable entity key.

    Parameters
    ----------
    repo_id : str
        Repository identifier (e.g. ``"ruoyi-vue"``).
    commit_sha : str
        40-character hex commit SHA.
    file_path : str
        Relative file path within the repository.
    entity_type : str
        Entity type tag (e.g. ``"class"``, ``"method"``, ``"function"``).
    qualified_name : str
        Fully-qualified entity name (e.g. Java FQN, Python dotted path).
    start_line : int or str
        1-based start line number.
    end_line : int or str
        1-based end line number.

    Returns
    -------
    str
        64-character lowercase hex SHA-256 digest.

    Raises
    ------
    TypeError
        If any argument is ``None``.
    """
    normalized_path = _normalize_file_path(str(file_path))

    # Convert line numbers to strings (they may arrive as int or str).
    start_str = str(int(start_line))
    end_str = str(int(end_line))

    payload = "|".join([
        str(repo_id),
        str(commit_sha),
        normalized_path,
        str(entity_type),
        str(qualified_name),
        start_str,
        end_str,
    ])

    # Ensure no trailing whitespace or newline (SPEC requirement).
    payload = payload.strip()

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_stable_key_from_dict(data: Dict[str, Any]) -> str:
    """Compute the stable entity key from a dictionary.

    The dictionary must contain the keys:
    ``repo_id``, ``commit_sha``, ``file_path``, ``entity_type``,
    ``qualified_name``, ``start_line``, ``end_line``.

    This is convenient when working with JSON-loaded evaluation cases
    where gold entities are stored as objects.

    Parameters
    ----------
    data : dict
        Dictionary with the seven required fields.

    Returns
    -------
    str
        64-character lowercase hex SHA-256 digest.

    Raises
    ------
    KeyError
        If a required field is missing.
    """
    required_keys = [
        "repo_id",
        "commit_sha",
        "file_path",
        "entity_type",
        "qualified_name",
        "start_line",
        "end_line",
    ]
    missing = [k for k in required_keys if k not in data]
    if missing:
        raise KeyError(
            f"Missing required field(s) for stable entity key: {missing}"
        )

    return compute_stable_key(
        repo_id=data["repo_id"],
        commit_sha=data["commit_sha"],
        file_path=data["file_path"],
        entity_type=data["entity_type"],
        qualified_name=data["qualified_name"],
        start_line=data["start_line"],
        end_line=data["end_line"],
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Compute the stable entity key (SHA-256) as defined in "
            "SPEC.md Section 7.5. Used in gold labels instead of "
            "volatile database auto-increment IDs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python stable_entity_key.py \\\n"
            "      --repo-id ruoyi-vue \\\n"
            "      --commit-sha 41720e6... \\\n"
            "      --file-path src/Main.java \\\n"
            "      --entity-type class \\\n"
            "      --qualified-name com.example.Main \\\n"
            "      --start-line 1 \\\n"
            "      --end-line 50"
        ),
    )
    parser.add_argument(
        "--repo-id",
        required=True,
        help="Repository identifier (e.g. 'ruoyi-vue').",
    )
    parser.add_argument(
        "--commit-sha",
        required=True,
        help="40-character hex commit SHA.",
    )
    parser.add_argument(
        "--file-path",
        required=True,
        help="Relative file path within the repository.",
    )
    parser.add_argument(
        "--entity-type",
        required=True,
        help="Entity type (e.g. 'class', 'method', 'function').",
    )
    parser.add_argument(
        "--qualified-name",
        required=True,
        help="Fully-qualified entity name.",
    )
    parser.add_argument(
        "--start-line",
        required=True,
        type=int,
        help="1-based start line number.",
    )
    parser.add_argument(
        "--end-line",
        required=True,
        type=int,
        help="1-based end line number.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints the hex digest to stdout.

    Returns 0 on success, 2 on argument errors.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        key = compute_stable_key(
            repo_id=args.repo_id,
            commit_sha=args.commit_sha,
            file_path=args.file_path,
            entity_type=args.entity_type,
            qualified_name=args.qualified_name,
            start_line=args.start_line,
            end_line=args.end_line,
        )
    except (TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
