#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix snapshot consistency for the pilot-current.jsonl evaluation dataset.

This script ensures every gold_entity, gold_node, and gold_edge in all 36
records correctly reflects whether the corresponding item exists in the
scan snapshot (code_entities.json / code_relations.json).

It also enforces cross-field consistency rules:
  - indexed_in_system flags match snapshot presence
  - must_recall entities are all indexed (or downgraded to source_only)
  - chain_complete matches edge indexing state
  - system_answerable matches the overall indexed state
  - source_evidence is present for indexed_in_system=false entities
  - expected_uncertainties are present where needed

Usage::

    python fix_snapshot_consistency.py \\
        --dataset ../datasets/pilot-current.jsonl \\
        --entities ../runtime/pilot/snapshot/code_entities.json \\
        --relations ../runtime/pilot/snapshot/code_relations.json \\
        --repo /path/to/ruoyi-vue
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Ensure sibling ``stable_entity_key`` module is importable.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from stable_entity_key import compute_stable_key  # noqa: E402


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file."""
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
# Change tracking
# ---------------------------------------------------------------------------

class ChangeTracker:
    """Track all changes made during the fix process."""

    def __init__(self) -> None:
        self.changes: List[str] = []
        self.entities_indexed_true = 0
        self.entities_indexed_false = 0
        self.nodes_indexed_true = 0
        self.nodes_indexed_false = 0
        self.edges_indexed_true = 0
        self.edges_indexed_false = 0
        self.missing_reasons: Dict[str, int] = {}
        self.chain_complete_true = 0
        self.chain_complete_false = 0
        self.system_answerable_counts: Dict[str, int] = {}
        self.records_fixed: Set[str] = set()

    def record_change(self, qid: str, description: str) -> None:
        self.changes.append(f"[{qid}] {description}")
        self.records_fixed.add(qid)

    def count_missing_reason(self, reason: str) -> None:
        self.missing_reasons[reason] = self.missing_reasons.get(reason, 0) + 1

    def print_summary(self) -> None:
        print("\n" + "=" * 72)
        print("FIX SUMMARY")
        print("=" * 72)
        print(f"  Total records fixed:          {len(self.records_fixed)}")
        print(f"  Total changes made:           {len(self.changes)}")
        print()
        print("  Entity indexing:")
        print(f"    indexed_in_system=true:     {self.entities_indexed_true}")
        print(f"    indexed_in_system=false:    {self.entities_indexed_false}")
        if self.missing_reasons:
            for reason, count in sorted(self.missing_reasons.items()):
                print(f"      {reason}: {count}")
        print()
        print("  Node indexing:")
        print(f"    indexed_in_system=true:     {self.nodes_indexed_true}")
        print(f"    indexed_in_system=false:    {self.nodes_indexed_false}")
        print()
        print("  Edge indexing:")
        print(f"    indexed_in_system=true:     {self.edges_indexed_true}")
        print(f"    indexed_in_system=false:    {self.edges_indexed_false}")
        print()
        print("  TRACE_CHAIN consistency:")
        print(f"    chain_complete=true:        {self.chain_complete_true}")
        print(f"    chain_complete=false:       {self.chain_complete_false}")
        if self.system_answerable_counts:
            print("  system_answerable distribution:")
            for level, count in sorted(self.system_answerable_counts.items()):
                print(f"    {level}: {count}")
        print()
        print("  Detailed changes:")
        for change in self.changes:
            print(f"    {change}")
        print("=" * 72)


# ---------------------------------------------------------------------------
# Fix functions
# ---------------------------------------------------------------------------

def fix_gold_entity(
    ent: Dict[str, Any],
    qid: str,
    snapshot_keys: Set[str],
    entity_lookup: Dict[str, Dict[str, Any]],
    repo_root: Optional[Path],
    tracker: ChangeTracker,
    idx: int,
) -> None:
    """Fix a single gold_entity's snapshot consistency fields."""
    key = ent.get("stable_entity_key", "")
    in_snapshot = key in snapshot_keys

    if in_snapshot:
        # Entity exists in snapshot
        old_indexed = ent.get("indexed_in_system")
        ent["indexed_in_system"] = True
        tracker.entities_indexed_true += 1

        # Remove any stale missing_reason / source_evidence
        if "missing_reason" in ent:
            del ent["missing_reason"]
        if "source_evidence" in ent:
            del ent["source_evidence"]

        # Ensure relevance is not source_only for indexed entities
        if ent.get("relevance") == "source_only":
            ent["relevance"] = "must_recall"
            tracker.record_change(
                qid,
                f"entity[{idx}] ({ent.get('qualified_name', '?')}): "
                f"relevance changed from source_only to must_recall (entity is indexed)",
            )

        if old_indexed is not True:
            tracker.record_change(
                qid,
                f"entity[{idx}] ({ent.get('qualified_name', '?')}): "
                f"indexed_in_system set to true (found in snapshot)",
            )
    else:
        # Entity NOT in snapshot
        old_indexed = ent.get("indexed_in_system")
        ent["indexed_in_system"] = False
        tracker.entities_indexed_false += 1

        # Determine missing_reason
        entity_type = ent.get("entity_type", "")
        if entity_type == "frontend_api_call":
            missing_reason = "dynamic_url"
        else:
            missing_reason = "not_in_scan_snapshot"
        ent["missing_reason"] = missing_reason
        tracker.count_missing_reason(missing_reason)

        # Relevance must be source_only for unindexed entities
        old_rel = ent.get("relevance", "")
        if old_rel != "source_only":
            ent["relevance"] = "source_only"
            tracker.record_change(
                qid,
                f"entity[{idx}] ({ent.get('qualified_name', '?')}): "
                f"relevance changed from {old_rel} to source_only (not indexed)",
            )

        # Add source_evidence from the entity's own file_path / lines
        fp = ent.get("file_path", "")
        sl = ent.get("start_line", 0)
        el = ent.get("end_line", 0)
        if fp and sl and el:
            ent["source_evidence"] = {
                "file_path": fp,
                "start_line": sl,
                "end_line": el,
            }
        elif not ent.get("source_evidence"):
            # Fallback: try to find from snapshot or use defaults
            ent["source_evidence"] = {
                "file_path": fp or "unknown",
                "start_line": sl or 1,
                "end_line": el or 1,
            }

        if old_indexed is not False:
            tracker.record_change(
                qid,
                f"entity[{idx}] ({ent.get('qualified_name', '?')}): "
                f"indexed_in_system set to false, missing_reason={missing_reason}",
            )


def fix_gold_node(
    node: Dict[str, Any],
    qid: str,
    snapshot_keys: Set[str],
    tracker: ChangeTracker,
    idx: int,
) -> None:
    """Fix a single gold_node's snapshot consistency fields."""
    key = node.get("stable_entity_key", "")
    in_snapshot = key in snapshot_keys

    if in_snapshot:
        old_indexed = node.get("indexed_in_system")
        node["indexed_in_system"] = True
        tracker.nodes_indexed_true += 1

        # Remove any stale missing_reason
        if "missing_reason" in node:
            del node["missing_reason"]

        if old_indexed is not True:
            tracker.record_change(
                qid,
                f"node[{idx}] ({node.get('qualified_name', '?')}): "
                f"indexed_in_system set to true (found in snapshot)",
            )
    else:
        old_indexed = node.get("indexed_in_system")
        node["indexed_in_system"] = False
        tracker.nodes_indexed_false += 1

        # Determine missing_reason
        entity_type = node.get("entity_type", "")
        if entity_type == "frontend_api_call":
            missing_reason = "dynamic_url"
        else:
            missing_reason = "not_in_scan_snapshot"
        node["missing_reason"] = missing_reason
        tracker.count_missing_reason(missing_reason)

        if old_indexed is not False:
            tracker.record_change(
                qid,
                f"node[{idx}] ({node.get('qualified_name', '?')}): "
                f"indexed_in_system set to false, missing_reason={missing_reason}",
            )


def fix_gold_edge(
    edge: Dict[str, Any],
    qid: str,
    relation_set: Set[Tuple[str, str, str]],
    snapshot_keys: Set[str],
    gold_node_keys: Set[str],
    tracker: ChangeTracker,
    idx: int,
) -> None:
    """Fix a single gold_edge's snapshot consistency fields."""
    triple = (
        edge.get("source_key", ""),
        edge.get("target_key", ""),
        edge.get("relation_type", ""),
    )
    in_relations = triple in relation_set

    # Check if source/target are phantom keys
    src_key = edge.get("source_key", "")
    tgt_key = edge.get("target_key", "")
    src_exists = src_key in snapshot_keys or src_key in gold_node_keys
    tgt_exists = tgt_key in snapshot_keys or tgt_key in gold_node_keys

    if in_relations and src_exists and tgt_exists:
        old_indexed = edge.get("indexed_in_system")
        edge["indexed_in_system"] = True
        tracker.edges_indexed_true += 1

        if old_indexed is not True:
            tracker.record_change(
                qid,
                f"edge[{idx}] ({edge.get('relation_type', '?')}): "
                f"indexed_in_system set to true (found in snapshot relations)",
            )
    else:
        old_indexed = edge.get("indexed_in_system")
        edge["indexed_in_system"] = False
        tracker.edges_indexed_false += 1

        if old_indexed is not False:
            reasons = []
            if not in_relations:
                reasons.append("not in snapshot relations")
            if not src_exists:
                reasons.append("source key not in snapshot")
            if not tgt_exists:
                reasons.append("target key not in snapshot")
            tracker.record_change(
                qid,
                f"edge[{idx}] ({edge.get('relation_type', '?')}): "
                f"indexed_in_system set to false ({'; '.join(reasons)})",
            )


def fix_chain_complete_and_answerable(
    record: Dict[str, Any],
    tracker: ChangeTracker,
) -> None:
    """Fix chain_complete and system_answerable consistency."""
    qid = record.get("question_id", "")
    task_type = record.get("task_type", "")
    gold_entities = record.get("gold_entities", [])
    gold_nodes = record.get("gold_nodes", [])
    gold_edges = record.get("gold_edges", [])

    # Compute current state
    all_nodes_indexed = all(
        n.get("indexed_in_system") is True for n in gold_nodes
    ) if gold_nodes else True

    any_node_unindexed = any(
        n.get("indexed_in_system") is False for n in gold_nodes
    )

    all_edges_indexed = all(
        e.get("indexed_in_system") is True for e in gold_edges
    ) if gold_edges else True

    any_edge_unindexed = any(
        e.get("indexed_in_system") is False for e in gold_edges
    )

    all_must_recall_indexed = all(
        e.get("indexed_in_system") is True
        for e in gold_entities
        if e.get("relevance") == "must_recall"
    ) if any(e.get("relevance") == "must_recall" for e in gold_entities) else True

    any_must_recall_unindexed = any(
        e.get("indexed_in_system") is False
        for e in gold_entities
        if e.get("relevance") in ("must_recall", "source_only")
    )

    # ---------------------------------------------------------------
    # Fix chain_complete for TRACE_CHAIN records
    # ---------------------------------------------------------------
    if task_type == "TRACE_CHAIN" and gold_edges:
        if all_edges_indexed and all_nodes_indexed:
            old_cc = record.get("chain_complete")
            if old_cc is not True:
                record["chain_complete"] = True
                tracker.record_change(
                    qid,
                    f"chain_complete changed from {old_cc} to true "
                    f"(all nodes and edges are indexed)",
                )
            tracker.chain_complete_true += 1
        else:
            old_cc = record.get("chain_complete")
            if old_cc is not False:
                record["chain_complete"] = False
                tracker.record_change(
                    qid,
                    f"chain_complete changed from {old_cc} to false "
                    f"(not all nodes/edges are indexed)",
                )
            tracker.chain_complete_false += 1
    elif task_type == "TRACE_CHAIN":
        # No edges: chain_complete should be false
        old_cc = record.get("chain_complete")
        if old_cc is not False and old_cc is not None:
            record["chain_complete"] = False
            tracker.record_change(
                qid,
                f"chain_complete changed from {old_cc} to false (no edges)",
            )
        if record.get("chain_complete") is None:
            # Leave as None for records with no edges
            pass
        tracker.chain_complete_false += 1

    # ---------------------------------------------------------------
    # Fix system_answerable
    # ---------------------------------------------------------------
    old_sa = record.get("system_answerable", "")

    if task_type == "TRACE_CHAIN":
        if gold_edges:
            if all_edges_indexed and all_nodes_indexed and all_must_recall_indexed:
                new_sa = "full"
            elif any_node_unindexed or any_edge_unindexed:
                # Some indexed, some not
                has_any_indexed = (
                    any(n.get("indexed_in_system") is True for n in gold_nodes)
                    or any(e.get("indexed_in_system") is True for e in gold_edges)
                    or any(
                        e.get("indexed_in_system") is True
                        for e in gold_entities
                        if e.get("relevance") == "must_recall"
                    )
                )
                if has_any_indexed:
                    new_sa = "partial"
                else:
                    new_sa = "insufficient"
            else:
                new_sa = "full"
        else:
            # No edges: can't trace chain
            has_any_indexed = any(
                e.get("indexed_in_system") is True for e in gold_entities
            ) or any(
                n.get("indexed_in_system") is True for n in gold_nodes
            )
            has_any_unindexed = any(
                e.get("indexed_in_system") is False for e in gold_entities
            ) or any(
                n.get("indexed_in_system") is False for n in gold_nodes
            )
            if has_any_indexed and has_any_unindexed:
                new_sa = "partial"
            elif has_any_indexed and not has_any_unindexed:
                # All entities/nodes indexed but no edges -> can't fully trace
                # Check if there are nodes at all
                if gold_nodes:
                    new_sa = "partial"
                else:
                    # No nodes, no edges, entities are indexed
                    # This is insufficient because chain can't be traced
                    new_sa = "insufficient"
            else:
                new_sa = "insufficient"

    elif task_type == "CODE_QA":
        must_recall_entities = [
            e for e in gold_entities
            if e.get("relevance") in ("must_recall", "acceptable_alternative")
        ]
        if not gold_entities:
            # No entities to check - keep existing
            new_sa = old_sa
        elif all(
            e.get("indexed_in_system") is True for e in must_recall_entities
        ) and must_recall_entities:
            new_sa = "full"
        elif any(
            e.get("indexed_in_system") is True for e in must_recall_entities
        ):
            new_sa = "partial"
        else:
            # Either no must_recall entities (all source_only) or none indexed
            if must_recall_entities:
                new_sa = "insufficient"
            else:
                # All entities are source_only -> system can't recall them
                new_sa = "insufficient"

    elif task_type == "CHANGE_PLAN":
        if not gold_entities:
            # Keep existing system_answerable for records with no entities
            new_sa = old_sa
        elif all(
            e.get("indexed_in_system") is True
            for e in gold_entities
            if e.get("relevance") == "must_recall"
        ):
            new_sa = "full"
        else:
            new_sa = "partial"
    else:
        new_sa = old_sa

    if new_sa != old_sa:
        record["system_answerable"] = new_sa
        tracker.record_change(
            qid,
            f"system_answerable changed from '{old_sa}' to '{new_sa}'",
        )

    tracker.system_answerable_counts[new_sa] = (
        tracker.system_answerable_counts.get(new_sa, 0) + 1
    )


def fix_expected_uncertainties(
    record: Dict[str, Any],
    tracker: ChangeTracker,
) -> None:
    """Ensure expected_uncertainties is consistent with system_answerable."""
    qid = record.get("question_id", "")
    sa = record.get("system_answerable", "")
    eu = record.get("expected_uncertainties", [])

    if sa in ("partial", "insufficient") and not eu:
        # Need to add expected_uncertainties
        unindexed_entities = [
            e for e in record.get("gold_entities", [])
            if e.get("indexed_in_system") is False
        ]
        unindexed_nodes = [
            n for n in record.get("gold_nodes", [])
            if n.get("indexed_in_system") is False
        ]
        unindexed_edges = [
            e for e in record.get("gold_edges", [])
            if e.get("indexed_in_system") is False
        ]

        new_eu = []
        for ent in unindexed_entities:
            mr = ent.get("missing_reason", "unknown")
            qn = ent.get("qualified_name", "unknown")
            new_eu.append({
                "condition": f"Entity not indexed: {qn}",
                "description": (
                    f"The entity '{qn}' is not in the static index "
                    f"(reason: {mr}). The system cannot retrieve it."
                ),
            })
        for node in unindexed_nodes:
            mr = node.get("missing_reason", "unknown")
            qn = node.get("qualified_name", "unknown")
            new_eu.append({
                "condition": f"Node not indexed: {qn}",
                "description": (
                    f"The graph node '{qn}' is not in the static index "
                    f"(reason: {mr}). The trace chain cannot include it."
                ),
            })
        for edge in unindexed_edges:
            rt = edge.get("relation_type", "unknown")
            new_eu.append({
                "condition": f"Edge not indexed: {rt}",
                "description": (
                    f"The {rt} relation is not in the snapshot because "
                    f"the source or target node is not indexed."
                ),
            })

        if new_eu:
            record["expected_uncertainties"] = new_eu
            tracker.record_change(
                qid,
                f"Added {len(new_eu)} expected_uncertainties for "
                f"system_answerable={sa}",
            )

    elif sa == "full" and eu:
        # Full answerability should not have expected_uncertainties
        # (unless they are about acceptable alternatives)
        pass  # Keep existing uncertainties for full records


def add_missing_gold_nodes_for_trace_chain(
    record: Dict[str, Any],
    snapshot_keys: Set[str],
    entity_lookup: Dict[str, Dict[str, Any]],
    tracker: ChangeTracker,
) -> None:
    """For TRACE_CHAIN records that have gold_entities but no gold_nodes,
    create gold_nodes from the entities to enable proper consistency checks.
    """
    qid = record.get("question_id", "")
    task_type = record.get("task_type", "")

    if task_type != "TRACE_CHAIN":
        return

    gold_entities = record.get("gold_entities", [])
    gold_nodes = record.get("gold_nodes", [])

    if not gold_entities:
        return

    if gold_nodes:
        # Already has nodes - check if all entities have corresponding nodes
        node_keys = {n.get("stable_entity_key") for n in gold_nodes}
        entity_keys = {e.get("stable_entity_key") for e in gold_entities}
        missing = entity_keys - node_keys
        if not missing:
            return
        # Add missing nodes
        order = len(gold_nodes)
        for ent in gold_entities:
            if ent.get("stable_entity_key") in missing:
                key = ent["stable_entity_key"]
                in_snapshot = key in snapshot_keys
                node = {
                    "stable_entity_key": key,
                    "entity_type": ent.get("entity_type", ""),
                    "qualified_name": ent.get("qualified_name", ""),
                    "file_path": ent.get("file_path", ""),
                    "order": order,
                    "indexed_in_system": in_snapshot,
                }
                if not in_snapshot:
                    entity_type = ent.get("entity_type", "")
                    node["missing_reason"] = (
                        "dynamic_url" if entity_type == "frontend_api_call"
                        else "not_in_scan_snapshot"
                    )
                    tracker.nodes_indexed_false += 1
                    tracker.count_missing_reason(node["missing_reason"])
                else:
                    tracker.nodes_indexed_true += 1
                gold_nodes.append(node)
                order += 1
                tracker.record_change(
                    qid,
                    f"Added missing gold_node for entity {ent.get('qualified_name', '?')} "
                    f"(indexed_in_system={in_snapshot})",
                )
    else:
        # No nodes at all - create from entities
        new_nodes = []
        for order, ent in enumerate(gold_entities):
            key = ent.get("stable_entity_key", "")
            in_snapshot = key in snapshot_keys
            node = {
                "stable_entity_key": key,
                "entity_type": ent.get("entity_type", ""),
                "qualified_name": ent.get("qualified_name", ""),
                "file_path": ent.get("file_path", ""),
                "order": order,
                "indexed_in_system": in_snapshot,
            }
            if not in_snapshot:
                entity_type = ent.get("entity_type", "")
                node["missing_reason"] = (
                    "dynamic_url" if entity_type == "frontend_api_call"
                    else "not_in_scan_snapshot"
                )
                tracker.nodes_indexed_false += 1
                tracker.count_missing_reason(node["missing_reason"])
            else:
                tracker.nodes_indexed_true += 1
            new_nodes.append(node)

        record["gold_nodes"] = new_nodes
        tracker.record_change(
            qid,
            f"Created {len(new_nodes)} gold_nodes from gold_entities "
            f"(TRACE_CHAIN record had no nodes)",
        )


# ---------------------------------------------------------------------------
# Special fixes for specific records
# ---------------------------------------------------------------------------

def apply_special_fixes(
    record: Dict[str, Any],
    snapshot_keys: Set[str],
    tracker: ChangeTracker,
) -> None:
    """Apply record-specific fixes that go beyond the general rules."""
    qid = record.get("question_id", "")

    # trace-chain-0024: source_answerable should be true
    if qid == "ruoyi-trace-chain-0024":
        if record.get("source_answerable") is not True:
            record["source_answerable"] = True
            tracker.record_change(
                qid,
                "source_answerable set to true (human can read source to answer)",
            )


# ---------------------------------------------------------------------------
# Main fix driver
# ---------------------------------------------------------------------------

def fix_dataset(
    dataset_path: Path,
    entities_path: Path,
    relations_path: Path,
    repo_root: Optional[Path] = None,
) -> None:
    """Fix all records in the dataset for snapshot consistency."""
    # Load data
    print(f"Loading dataset from {dataset_path}...")
    records = load_jsonl(dataset_path)
    print(f"  {len(records)} records loaded")

    print(f"Loading snapshot entities from {entities_path}...")
    entities = load_json(entities_path)
    snapshot_keys = build_entity_key_set(entities)
    entity_lookup = build_entity_lookup(entities)
    print(f"  {len(entities)} entities loaded, {len(snapshot_keys)} unique keys")

    print(f"Loading snapshot relations from {relations_path}...")
    relations = load_json(relations_path)
    relation_set = build_relation_set(relations)
    print(f"  {len(relations)} relations loaded, {len(relation_set)} unique triples")

    tracker = ChangeTracker()

    # Process each record
    for record in records:
        qid = record.get("question_id", "<unknown>")
        task_type = record.get("task_type", "")

        gold_entities = record.get("gold_entities", [])
        gold_nodes = record.get("gold_nodes", [])
        gold_edges = record.get("gold_edges", [])

        # Step 0: For TRACE_CHAIN records with entities but no nodes,
        # create gold_nodes first (before fixing entities)
        add_missing_gold_nodes_for_trace_chain(
            record, snapshot_keys, entity_lookup, tracker
        )
        # Re-read after potential modification
        gold_nodes = record.get("gold_nodes", [])

        # Step 1: Fix gold_entities
        for idx, ent in enumerate(gold_entities):
            fix_gold_entity(
                ent, qid, snapshot_keys, entity_lookup, repo_root, tracker, idx
            )

        # Step 2: Fix gold_nodes
        for idx, node in enumerate(gold_nodes):
            fix_gold_node(node, qid, snapshot_keys, tracker, idx)

        # Step 3: Fix gold_edges
        gold_node_keys = {n.get("stable_entity_key", "") for n in gold_nodes}
        for idx, edge in enumerate(gold_edges):
            fix_gold_edge(
                edge, qid, relation_set, snapshot_keys, gold_node_keys, tracker, idx
            )

        # Step 4: Apply special fixes
        apply_special_fixes(record, snapshot_keys, tracker)

        # Step 5: Fix chain_complete and system_answerable
        fix_chain_complete_and_answerable(record, tracker)

        # Step 6: Fix expected_uncertainties
        fix_expected_uncertainties(record, tracker)

    # Write fixed dataset
    print(f"\nWriting fixed dataset to {dataset_path}...")
    with open(dataset_path, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"  {len(records)} records written")

    # Compute SHA-256
    with open(dataset_path, "rb") as fh:
        sha256 = hashlib.sha256(fh.read()).hexdigest()
    print(f"  SHA-256: {sha256}")

    # Print summary
    tracker.print_summary()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fix snapshot consistency for the pilot evaluation dataset. "
            "Sets indexed_in_system flags, fixes chain_complete and "
            "system_answerable, adds source_evidence for missing entities."
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    for label, path in [("dataset", args.dataset), ("entities", args.entities),
                        ("relations", args.relations)]:
        if not path.is_file():
            print(f"Error: {label} file not found: {path}", file=sys.stderr)
            return 2

    if args.repo and not args.repo.is_dir():
        print(f"Error: repo directory not found: {args.repo}", file=sys.stderr)
        return 2

    try:
        fix_dataset(
            dataset_path=args.dataset,
            entities_path=args.entities,
            relations_path=args.relations,
            repo_root=args.repo,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
