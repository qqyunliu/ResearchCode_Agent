#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot-aware gold data validator for ResearchCode-Agent evaluation.

Validates evaluation dataset records against the actual scan snapshot to ensure
consistency between gold annotations and the indexed state of the system.

This script enforces the v1.4.0 schema validation rules:
  1. indexed_in_system=true entities must exist in snapshot
  2. indexed_in_system=true edges must exist in snapshot relations
  3. indexed_in_system=false entities must have missing_reason + source_evidence
  4. must_recall entities must exist in snapshot (indexed_in_system=true)
  5. Stable key recomputation from snapshot data must match gold keys
  6. File path and line number verification against repository
  7. chain_complete consistency with gold_edges
  8. system_answerable consistency with indexed state

Usage::

    python validate_against_snapshot.py \\
        --dataset ../datasets/pilot-current.jsonl \\
        --entities ../runtime/pilot/snapshot/code_entities.json \\
        --relations ../runtime/pilot/snapshot/code_relations.json \\
        --repo /path/to/ruoyi-vue \\
        [--fix-mode]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Ensure sibling ``stable_entity_key`` module is importable when this script
# is invoked directly (``python validate_against_snapshot.py``).
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from stable_entity_key import compute_stable_key  # noqa: E402


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """A single validation failure."""
    question_id: str
    field: str
    rule: str
    reason: str

    def __str__(self) -> str:
        return (
            f"[{self.question_id}] field={self.field} "
            f"rule={self.rule}: {self.reason}"
        )


@dataclass
class ValidationResult:
    """Aggregated validation outcome."""
    total_records: int = 0
    violations: List[Violation] = field(default_factory=list)
    passing_records: int = 0

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def all_pass(self) -> bool:
        return len(self.violations) == 0


# ---------------------------------------------------------------------------
# Snapshot loaders
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file (one JSON object per line)."""
    records: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_no} of {path}: {exc}"
                ) from exc
    return records


def load_json(path: Path) -> Any:
    """Load a JSON file."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_entity_key_set(entities: List[Dict[str, Any]]) -> Set[str]:
    """Build a set of stable_entity_key values from snapshot entities."""
    return {e["stable_entity_key"] for e in entities if "stable_entity_key" in e}


def build_entity_lookup(
    entities: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a dict mapping stable_entity_key -> entity record."""
    lookup: Dict[str, Dict[str, Any]] = {}
    for e in entities:
        key = e.get("stable_entity_key")
        if key:
            lookup[key] = e
    return lookup


def build_relation_set(relations: List[Dict[str, Any]]) -> Set[Tuple[str, str, str]]:
    """Build a set of (source_key, target_key, relation_type) tuples."""
    return {
        (r["source_key"], r["target_key"], r["relation_type"])
        for r in relations
        if all(k in r for k in ("source_key", "target_key", "relation_type"))
    }


# ---------------------------------------------------------------------------
# File verification helpers
# ---------------------------------------------------------------------------

def _count_lines(file_path: Path) -> Optional[int]:
    """Return the number of lines in a file, or None if unreadable."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def verify_file_and_lines(
    repo_root: Path,
    file_path: str,
    start_line: int,
    end_line: int,
) -> Optional[str]:
    """Verify that *file_path* exists under *repo_root* and line range is valid.

    Returns ``None`` on success, or an error string on failure.
    """
    full_path = repo_root / file_path
    if not full_path.is_file():
        return f"file does not exist: {file_path}"
    line_count = _count_lines(full_path)
    if line_count is None:
        return f"cannot read file: {file_path}"
    if start_line < 1:
        return f"start_line {start_line} < 1 for {file_path}"
    if end_line < start_line:
        return f"end_line {end_line} < start_line {start_line} for {file_path}"
    if end_line > line_count:
        return (
            f"end_line {end_line} exceeds file length {line_count} "
            f"for {file_path}"
        )
    return None


# ---------------------------------------------------------------------------
# Per-record validation
# ---------------------------------------------------------------------------

def validate_record(
    record: Dict[str, Any],
    snapshot_keys: Set[str],
    entity_lookup: Dict[str, Dict[str, Any]],
    relation_set: Set[Tuple[str, str, str]],
    repo_root: Optional[Path],
    fix_mode: bool = False,
) -> List[Violation]:
    """Validate a single dataset record against the snapshot.

    Parameters
    ----------
    record : dict
        A single JSONL evaluation record.
    snapshot_keys : set of str
        All stable_entity_key values present in the snapshot entities.
    entity_lookup : dict
        Mapping from stable_entity_key to snapshot entity record.
    relation_set : set of (str, str, str)
        All (source_key, target_key, relation_type) in the snapshot.
    repo_root : Path or None
        Root directory of the repository at the fixed commit.  When *None*,
        file-existence and line-range checks are skipped.
    fix_mode : bool
        Reserved for future auto-fix capability (currently unused).

    Returns
    -------
    list of Violation
    """
    qid: str = record.get("question_id", "<unknown>")
    violations: List[Violation] = []

    gold_entities = record.get("gold_entities") or []
    gold_nodes = record.get("gold_nodes") or []
    gold_edges = record.get("gold_edges") or []
    system_answerable = record.get("system_answerable", "")
    chain_complete = record.get("chain_complete")
    task_type = record.get("task_type", "")
    repo_id = record.get("repo_id", "")
    commit_sha = record.get("commit_sha", "")

    # ------------------------------------------------------------------
    # Helper: add violation
    # ------------------------------------------------------------------
    def _v(field_: str, rule_: str, reason_: str) -> None:
        violations.append(Violation(qid, field_, rule_, reason_))

    # ==================================================================
    # Rule 1: indexed_in_system=true entity/node key must exist in snapshot
    # ==================================================================
    for idx, ent in enumerate(gold_entities):
        if ent.get("indexed_in_system") is True:
            key = ent.get("stable_entity_key", "")
            if key not in snapshot_keys:
                _v(
                    f"gold_entities[{idx}]",
                    "indexed_entity_in_snapshot",
                    f"indexed_in_system=true but key {key[:16]}... "
                    f"not found in snapshot",
                )

    for idx, node in enumerate(gold_nodes):
        if node.get("indexed_in_system") is True:
            key = node.get("stable_entity_key", "")
            if key not in snapshot_keys:
                _v(
                    f"gold_nodes[{idx}]",
                    "indexed_node_in_snapshot",
                    f"indexed_in_system=true but key {key[:16]}... "
                    f"not found in snapshot",
                )

    # ==================================================================
    # Rule 2: indexed_in_system=true edge must exist in snapshot relations
    # ==================================================================
    for idx, edge in enumerate(gold_edges):
        if edge.get("indexed_in_system") is True:
            triple = (
                edge.get("source_key", ""),
                edge.get("target_key", ""),
                edge.get("relation_type", ""),
            )
            if triple not in relation_set:
                _v(
                    f"gold_edges[{idx}]",
                    "indexed_edge_in_relations",
                    f"indexed_in_system=true but edge "
                    f"({triple[2]}) {triple[0][:12]}...->{triple[1][:12]}... "
                    f"not found in snapshot relations",
                )

    # ==================================================================
    # Rule 3: indexed_in_system=false entity/node must have supporting data
    # ==================================================================
    for idx, ent in enumerate(gold_entities):
        if ent.get("indexed_in_system") is False:
            # Must have missing_reason
            if not ent.get("missing_reason"):
                _v(
                    f"gold_entities[{idx}]",
                    "missing_reason_required",
                    "indexed_in_system=false but missing_reason is absent or empty",
                )
            # Must have source_evidence
            se = ent.get("source_evidence")
            if not se:
                _v(
                    f"gold_entities[{idx}]",
                    "source_evidence_required",
                    "indexed_in_system=false but source_evidence is absent",
                )
            else:
                # source_evidence must have required sub-fields
                for sub in ("file_path", "start_line", "end_line"):
                    if sub not in se:
                        _v(
                            f"gold_entities[{idx}].source_evidence",
                            "source_evidence_fields",
                            f"source_evidence missing required field: {sub}",
                        )
                # File existence check for source_evidence
                if repo_root and all(k in se for k in ("file_path", "start_line", "end_line")):
                    err = verify_file_and_lines(
                        repo_root, se["file_path"], se["start_line"], se["end_line"]
                    )
                    if err:
                        _v(
                            f"gold_entities[{idx}].source_evidence",
                            "source_evidence_file_exists",
                            err,
                        )

            # system_answerable must NOT be "full"
            if system_answerable == "full":
                _v(
                    f"gold_entities[{idx}]",
                    "system_answerable_consistency",
                    "indexed_in_system=false but system_answerable='full'",
                )
            # relevance must be "source_only"
            rel = ent.get("relevance", "")
            if rel == "must_recall":
                _v(
                    f"gold_entities[{idx}]",
                    "relevance_source_only",
                    "indexed_in_system=false but relevance='must_recall' "
                    "(should be 'source_only')",
                )

    for idx, node in enumerate(gold_nodes):
        if node.get("indexed_in_system") is False:
            if not node.get("missing_reason"):
                _v(
                    f"gold_nodes[{idx}]",
                    "missing_reason_required",
                    "indexed_in_system=false but missing_reason is absent or empty",
                )

    # ==================================================================
    # Rule 4: must_recall entities must have indexed_in_system=true
    # ==================================================================
    for idx, ent in enumerate(gold_entities):
        if ent.get("relevance") == "must_recall":
            indexed = ent.get("indexed_in_system")
            # Only flag if indexed_in_system is explicitly set to false
            if indexed is False:
                _v(
                    f"gold_entities[{idx}]",
                    "must_recall_indexed",
                    "relevance='must_recall' but indexed_in_system=false",
                )

    # ==================================================================
    # Rule 5: Stable key recomputation for indexed_in_system=true entities
    # ==================================================================
    if repo_id and commit_sha:
        for idx, ent in enumerate(gold_entities):
            if ent.get("indexed_in_system") is not True:
                continue
            key = ent.get("stable_entity_key", "")
            snap_entity = entity_lookup.get(key)
            if snap_entity is None:
                # Already caught by Rule 1
                continue
            # Recompute from snapshot entity data
            try:
                recomputed = compute_stable_key(
                    repo_id=repo_id,
                    commit_sha=commit_sha,
                    file_path=snap_entity.get("file_path", ""),
                    entity_type=snap_entity.get("entity_type", ""),
                    qualified_name=snap_entity.get("qualified_name", ""),
                    start_line=snap_entity.get("start_line", 0),
                    end_line=snap_entity.get("end_line", 0),
                )
            except (KeyError, TypeError, ValueError) as exc:
                _v(
                    f"gold_entities[{idx}]",
                    "stable_key_recompute",
                    f"failed to recompute stable key from snapshot: {exc}",
                )
                continue
            if recomputed != key:
                _v(
                    f"gold_entities[{idx}]",
                    "stable_key_recompute",
                    f"gold key {key[:16]}... != recomputed {recomputed[:16]}...",
                )

        for idx, node in enumerate(gold_nodes):
            if node.get("indexed_in_system") is not True:
                continue
            key = node.get("stable_entity_key", "")
            snap_entity = entity_lookup.get(key)
            if snap_entity is None:
                continue
            try:
                recomputed = compute_stable_key(
                    repo_id=repo_id,
                    commit_sha=commit_sha,
                    file_path=snap_entity.get("file_path", ""),
                    entity_type=snap_entity.get("entity_type", ""),
                    qualified_name=snap_entity.get("qualified_name", ""),
                    start_line=snap_entity.get("start_line", 0),
                    end_line=snap_entity.get("end_line", 0),
                )
            except (KeyError, TypeError, ValueError) as exc:
                _v(
                    f"gold_nodes[{idx}]",
                    "stable_key_recompute",
                    f"failed to recompute stable key from snapshot: {exc}",
                )
                continue
            if recomputed != key:
                _v(
                    f"gold_nodes[{idx}]",
                    "stable_key_recompute",
                    f"gold key {key[:16]}... != recomputed {recomputed[:16]}...",
                )

    # ==================================================================
    # Rule 6: File path and line number verification
    # ==================================================================
    if repo_root:
        for idx, ent in enumerate(gold_entities):
            fp = ent.get("file_path", "")
            sl = ent.get("start_line", 0)
            el = ent.get("end_line", 0)
            if fp and sl and el:
                err = verify_file_and_lines(repo_root, fp, sl, el)
                if err:
                    _v(
                        f"gold_entities[{idx}]",
                        "file_path_verification",
                        err,
                    )

    # ==================================================================
    # Rule 7: chain_complete consistency
    # ==================================================================
    if gold_edges:
        any_edge_unindexed = any(
            e.get("indexed_in_system") is False for e in gold_edges
        )
        all_edges_indexed = all(
            e.get("indexed_in_system") is not False for e in gold_edges
        )

        if chain_complete is True and any_edge_unindexed:
            _v(
                "chain_complete",
                "chain_complete_edges_indexed",
                "chain_complete=true but at least one gold_edge has "
                "indexed_in_system=false",
            )

        if any_edge_unindexed and chain_complete is True:
            # Already reported above; avoid duplicate
            pass

        # For TRACE_CHAIN records: if chain_complete=false,
        # system_answerable must NOT be "full"
        if (
            task_type == "TRACE_CHAIN"
            and chain_complete is False
            and system_answerable == "full"
        ):
            _v(
                "system_answerable",
                "chain_complete_system_answerable",
                "chain_complete=false for TRACE_CHAIN but "
                "system_answerable='full'",
            )

    # ==================================================================
    # Rule 8: system_answerable consistency
    # ==================================================================
    if system_answerable == "full":
        # All required entities must be indexed
        for idx, ent in enumerate(gold_entities):
            rel = ent.get("relevance", "")
            if rel in ("must_recall", "acceptable_alternative"):
                if ent.get("indexed_in_system") is False:
                    _v(
                        f"gold_entities[{idx}]",
                        "system_answerable_full_requires_indexed",
                        f"system_answerable='full' but entity with "
                        f"relevance='{rel}' has indexed_in_system=false",
                    )
        # All required nodes must be indexed
        for idx, node in enumerate(gold_nodes):
            if node.get("indexed_in_system") is False:
                _v(
                    f"gold_nodes[{idx}]",
                    "system_answerable_full_requires_indexed_nodes",
                    "system_answerable='full' but node has "
                    "indexed_in_system=false",
                )
        # All required edges must be indexed and chain_complete must be true
        if gold_edges:
            for idx, edge in enumerate(gold_edges):
                if edge.get("indexed_in_system") is False:
                    _v(
                        f"gold_edges[{idx}]",
                        "system_answerable_full_requires_indexed_edges",
                        "system_answerable='full' but edge has "
                        "indexed_in_system=false",
                    )
            if chain_complete is False:
                _v(
                    "chain_complete",
                    "system_answerable_full_chain_complete",
                    "system_answerable='full' but chain_complete=false",
                )

    elif system_answerable == "partial":
        # At least some entities/edges indexed, at least one not indexed
        all_items = (
            [e for e in gold_entities if e.get("relevance") in ("must_recall", "acceptable_alternative")]
            + list(gold_nodes)
            + list(gold_edges)
        )
        has_indexed = any(
            item.get("indexed_in_system") is True for item in all_items
        )
        has_unindexed = any(
            item.get("indexed_in_system") is False for item in all_items
        )
        if all_items and not has_indexed and not has_unindexed:
            # No indexed_in_system fields set at all -- skip check
            pass
        elif all_items and has_indexed and not has_unindexed:
            _v(
                "system_answerable",
                "system_answerable_partial_mixed",
                "system_answerable='partial' but all items with "
                "indexed_in_system are indexed (expected at least one "
                "unindexed)",
            )

    elif system_answerable == "insufficient":
        # Key evidence must be missing from index
        all_items = (
            [e for e in gold_entities if e.get("relevance") == "must_recall"]
            + list(gold_nodes)
        )
        has_unindexed = any(
            item.get("indexed_in_system") is False for item in all_items
        )
        if all_items and not has_unindexed:
            # Only flag if there are items and all are indexed
            all_indexed = all(
                item.get("indexed_in_system") is True for item in all_items
            )
            if all_indexed and all_items:
                _v(
                    "system_answerable",
                    "system_answerable_insufficient_missing",
                    "system_answerable='insufficient' but all required "
                    "entities/nodes have indexed_in_system=true",
                )

    return violations


# ---------------------------------------------------------------------------
# Main validation driver
# ---------------------------------------------------------------------------

def validate_dataset(
    dataset_path: Path,
    entities_path: Path,
    relations_path: Path,
    repo_root: Optional[Path] = None,
    fix_mode: bool = False,
) -> ValidationResult:
    """Validate all records in a dataset against snapshot data.

    Parameters
    ----------
    dataset_path : Path
        Path to the JSONL dataset file.
    entities_path : Path
        Path to the snapshot code_entities.json.
    relations_path : Path
        Path to the snapshot code_relations.json.
    repo_root : Path or None
        Root directory of the repository at the fixed commit.
    fix_mode : bool
        Reserved for future auto-fix capability.

    Returns
    -------
    ValidationResult
    """
    records = load_jsonl(dataset_path)
    entities = load_json(entities_path)
    relations = load_json(relations_path)

    snapshot_keys = build_entity_key_set(entities)
    entity_lookup = build_entity_lookup(entities)
    relation_set = build_relation_set(relations)

    result = ValidationResult(total_records=len(records))

    # Track which records had violations
    records_with_violations: Set[str] = set()

    for record in records:
        qid = record.get("question_id", "<unknown>")
        vios = validate_record(
            record,
            snapshot_keys,
            entity_lookup,
            relation_set,
            repo_root,
            fix_mode,
        )
        if vios:
            records_with_violations.add(qid)
            result.violations.extend(vios)

    result.passing_records = result.total_records - len(records_with_violations)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate gold evaluation data against the scan snapshot. "
            "Checks consistency of indexed_in_system flags, stable keys, "
            "file paths, chain completeness, and system_answerable levels."
        ),
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="Path to the JSONL dataset file.",
    )
    parser.add_argument(
        "--entities",
        required=True,
        type=Path,
        help="Path to the snapshot code_entities.json.",
    )
    parser.add_argument(
        "--relations",
        required=True,
        type=Path,
        help="Path to the snapshot code_relations.json.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Root path of the repository at the fixed commit.",
    )
    parser.add_argument(
        "--fix-mode",
        action="store_true",
        default=False,
        help="Reserved for future auto-fix capability (currently unused).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 if all records pass, 1 otherwise."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Validate paths exist
    for label, path in [("dataset", args.dataset), ("entities", args.entities),
                        ("relations", args.relations)]:
        if not path.is_file():
            print(f"Error: {label} file not found: {path}", file=sys.stderr)
            return 2

    if args.repo and not args.repo.is_dir():
        print(f"Error: repo directory not found: {args.repo}", file=sys.stderr)
        return 2

    try:
        result = validate_dataset(
            dataset_path=args.dataset,
            entities_path=args.entities,
            relations_path=args.relations,
            repo_root=args.repo,
            fix_mode=args.fix_mode,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Error loading data: {exc}", file=sys.stderr)
        return 2

    # Print violations
    if result.violations:
        print(f"\n{'='*72}")
        print("VIOLATIONS")
        print(f"{'='*72}")
        for vio in result.violations:
            print(f"  {vio}")
    else:
        print("\nAll records passed validation.")

    # Print summary
    print(f"\n{'='*72}")
    print("SUMMARY")
    print(f"{'='*72}")
    print(f"  Total records checked: {result.total_records}")
    print(f"  Violations found:      {result.violation_count}")
    print(f"  Records passing:       {result.passing_records}")
    print(f"{'='*72}")

    return 0 if result.all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
