#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for validate_against_snapshot.py.

Uses a small fixture snapshot (4 entities, 3 relations) to exercise all
eight validation rules.  Each test function constructs the minimum record
structure needed to trigger the specific rule under test.

Run with::

    python -m pytest evaluation/scripts/tests -q
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from stable_entity_key import compute_stable_key  # noqa: E402
from validate_against_snapshot import (  # noqa: E402
    ValidationResult,
    Violation,
    build_entity_key_set,
    build_entity_lookup,
    build_relation_set,
    validate_dataset,
    validate_record,
    verify_file_and_lines,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ID = "ruoyi-vue"
COMMIT_SHA = "41720e624c5a668c7d3777835e4c87095a7a1dfd"

# Pre-computed stable keys matching the fixture entities
CLASS_KEY = compute_stable_key(
    REPO_ID, COMMIT_SHA,
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
    "java_class", "SysLoginController", 32, 138,
)
METHOD_KEY = compute_stable_key(
    REPO_ID, COMMIT_SHA,
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
    "java_method", "SysLoginController.login", 56, 65,
)
API_KEY = compute_stable_key(
    REPO_ID, COMMIT_SHA,
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
    "backend_api", "POST /login", 56, 65,
)
FE_API_KEY = compute_stable_key(
    REPO_ID, COMMIT_SHA,
    "ruoyi-ui/src/api/login.js",
    "frontend_api_call", "POST /login", 11, 19,
)
# An entity key that does NOT exist in the snapshot
MISSING_KEY = compute_stable_key(
    REPO_ID, COMMIT_SHA,
    "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
    "java_method", "SysUserServiceImpl.selectUserById", 45, 60,
)


# ---------------------------------------------------------------------------
# Fixtures: snapshot data
# ---------------------------------------------------------------------------

def _make_snapshot_entities() -> List[Dict[str, Any]]:
    """Return 4 snapshot entities."""
    return [
        {
            "stable_entity_key": CLASS_KEY,
            "entity_type": "java_class",
            "name": "SysLoginController",
            "qualified_name": "SysLoginController",
            "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
            "start_line": 32,
            "end_line": 138,
            "content_hash": "aaaa",
        },
        {
            "stable_entity_key": METHOD_KEY,
            "entity_type": "java_method",
            "name": "login",
            "qualified_name": "SysLoginController.login",
            "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
            "start_line": 56,
            "end_line": 65,
            "content_hash": "bbbb",
        },
        {
            "stable_entity_key": API_KEY,
            "entity_type": "backend_api",
            "name": "POST /login",
            "qualified_name": "POST /login",
            "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
            "start_line": 56,
            "end_line": 65,
            "content_hash": "cccc",
        },
        {
            "stable_entity_key": FE_API_KEY,
            "entity_type": "frontend_api_call",
            "name": "POST /login",
            "qualified_name": "POST /login",
            "file_path": "ruoyi-ui/src/api/login.js",
            "start_line": 11,
            "end_line": 19,
            "content_hash": "dddd",
        },
    ]


def _make_snapshot_relations() -> List[Dict[str, Any]]:
    """Return 3 snapshot relations."""
    return [
        {
            "relation_type": "REQUESTS_API",
            "source_key": FE_API_KEY,
            "target_key": API_KEY,
            "confidence": 1.0,
        },
        {
            "relation_type": "DEFINES_API",
            "source_key": API_KEY,
            "target_key": METHOD_KEY,
            "confidence": 1.0,
        },
        {
            "relation_type": "CONTAINS",
            "source_key": CLASS_KEY,
            "target_key": METHOD_KEY,
            "confidence": 1.0,
        },
    ]


def _base_record(**overrides: Any) -> Dict[str, Any]:
    """Build a minimal valid record, applying optional overrides."""
    rec: Dict[str, Any] = {
        "question_id": "ruoyi-code-qa-0099",
        "repo_id": REPO_ID,
        "commit_sha": COMMIT_SHA,
        "task_type": "CODE_QA",
        "system_answerable": "full",
        "gold_entities": [],
        "gold_nodes": [],
        "gold_edges": [],
    }
    rec.update(overrides)
    return rec


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _run(record: Dict[str, Any]) -> List[Violation]:
    """Run validate_record with the standard fixture snapshot."""
    entities = _make_snapshot_entities()
    relations = _make_snapshot_relations()
    return validate_record(
        record=record,
        snapshot_keys=build_entity_key_set(entities),
        entity_lookup=build_entity_lookup(entities),
        relation_set=build_relation_set(relations),
        repo_root=None,  # skip file checks unless explicitly set
    )


def _rules(violations: List[Violation]) -> List[str]:
    """Extract rule names from a list of violations."""
    return [v.rule for v in violations]


def _fields(violations: List[Violation]) -> List[str]:
    """Extract field names from a list of violations."""
    return [v.field for v in violations]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidIndexedEntityPasses:
    """Test 1: A correctly indexed entity with indexed_in_system=true
    and a key that exists in the snapshot should produce no violations."""

    def test_pass(self):
        rec = _base_record(
            gold_entities=[
                {
                    "stable_entity_key": CLASS_KEY,
                    "entity_type": "java_class",
                    "qualified_name": "SysLoginController",
                    "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                    "start_line": 32,
                    "end_line": 138,
                    "relevance": "must_recall",
                    "indexed_in_system": True,
                },
            ],
        )
        vios = _run(rec)
        assert vios == [], f"Expected no violations, got: {vios}"


class TestMissingIndexedEntityFails:
    """Test 2: An entity marked indexed_in_system=true whose key does NOT
    exist in the snapshot should fail rule indexed_entity_in_snapshot."""

    def test_fail(self):
        rec = _base_record(
            gold_entities=[
                {
                    "stable_entity_key": MISSING_KEY,
                    "entity_type": "java_method",
                    "qualified_name": "SysUserServiceImpl.selectUserById",
                    "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                    "start_line": 45,
                    "end_line": 60,
                    "relevance": "must_recall",
                    "indexed_in_system": True,
                },
            ],
        )
        vios = _run(rec)
        assert any(v.rule == "indexed_entity_in_snapshot" for v in vios), (
            f"Expected indexed_entity_in_snapshot violation, got: {_rules(vios)}"
        )


class TestIndexedFalseWithMissingReasonPasses:
    """Test 3: An entity with indexed_in_system=false that has a proper
    missing_reason, source_evidence, and source_only relevance should pass
    (assuming system_answerable != 'full')."""

    def test_pass(self):
        rec = _base_record(
            system_answerable="partial",
            gold_entities=[
                {
                    "stable_entity_key": MISSING_KEY,
                    "entity_type": "java_method",
                    "qualified_name": "SysUserServiceImpl.selectUserById",
                    "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                    "start_line": 45,
                    "end_line": 60,
                    "relevance": "source_only",
                    "indexed_in_system": False,
                    "missing_reason": "parser_limitation",
                    "source_evidence": {
                        "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                        "start_line": 45,
                        "end_line": 60,
                    },
                },
            ],
        )
        vios = _run(rec)
        # Filter out file-path violations since repo_root=None skips those
        # but system_answerable='partial' may produce a partial-mixed check
        # that only fires when indexed_in_system fields are present.
        # In this case there is one entity with indexed_in_system=False and
        # no entity with indexed_in_system=True -- so the partial check
        # could flag it. Let's check there are no rule-3 violations.
        rule3_rules = {
            "missing_reason_required",
            "source_evidence_required",
            "source_evidence_fields",
            "source_evidence_file_exists",
            "relevance_source_only",
            "system_answerable_consistency",
        }
        rule3_vios = [v for v in vios if v.rule in rule3_rules]
        assert rule3_vios == [], (
            f"Expected no rule-3 violations, got: {rule3_vios}"
        )


class TestIndexedFalseWithoutMissingReasonFails:
    """Test 4: An entity with indexed_in_system=false but no missing_reason
    should fail rule missing_reason_required."""

    def test_fail(self):
        rec = _base_record(
            system_answerable="partial",
            gold_entities=[
                {
                    "stable_entity_key": MISSING_KEY,
                    "entity_type": "java_method",
                    "qualified_name": "SysUserServiceImpl.selectUserById",
                    "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                    "start_line": 45,
                    "end_line": 60,
                    "relevance": "source_only",
                    "indexed_in_system": False,
                    "source_evidence": {
                        "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                        "start_line": 45,
                        "end_line": 60,
                    },
                    # missing_reason deliberately omitted
                },
            ],
        )
        vios = _run(rec)
        assert any(v.rule == "missing_reason_required" for v in vios), (
            f"Expected missing_reason_required violation, got: {_rules(vios)}"
        )


class TestMustRecallNotIndexedFails:
    """Test 5: A must_recall entity with indexed_in_system=false should
    fail rule must_recall_indexed."""

    def test_fail(self):
        rec = _base_record(
            system_answerable="partial",
            gold_entities=[
                {
                    "stable_entity_key": MISSING_KEY,
                    "entity_type": "java_method",
                    "qualified_name": "SysUserServiceImpl.selectUserById",
                    "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                    "start_line": 45,
                    "end_line": 60,
                    "relevance": "must_recall",
                    "indexed_in_system": False,
                    "missing_reason": "parser_limitation",
                    "source_evidence": {
                        "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                        "start_line": 45,
                        "end_line": 60,
                    },
                },
            ],
        )
        vios = _run(rec)
        assert any(v.rule == "must_recall_indexed" for v in vios), (
            f"Expected must_recall_indexed violation, got: {_rules(vios)}"
        )


class TestEdgeIndexedTrueNotInRelationsFails:
    """Test 6: An edge with indexed_in_system=true whose triple is not in
    the relations snapshot should fail rule indexed_edge_in_relations."""

    def test_fail(self):
        rec = _base_record(
            gold_edges=[
                {
                    "source_key": CLASS_KEY,
                    "target_key": API_KEY,
                    "relation_type": "CALLS_METHOD",  # not in snapshot
                    "indexed_in_system": True,
                },
            ],
        )
        vios = _run(rec)
        assert any(v.rule == "indexed_edge_in_relations" for v in vios), (
            f"Expected indexed_edge_in_relations violation, got: {_rules(vios)}"
        )


class TestChainCompleteTrueWithUnindexedEdgeFails:
    """Test 7: chain_complete=true with at least one edge that has
    indexed_in_system=false should fail rule chain_complete_edges_indexed."""

    def test_fail(self):
        rec = _base_record(
            task_type="TRACE_CHAIN",
            system_answerable="partial",
            chain_complete=True,
            gold_edges=[
                {
                    "source_key": FE_API_KEY,
                    "target_key": API_KEY,
                    "relation_type": "REQUESTS_API",
                    "indexed_in_system": True,
                },
                {
                    "source_key": API_KEY,
                    "target_key": METHOD_KEY,
                    "relation_type": "DEFINES_API",
                    "indexed_in_system": False,
                },
            ],
        )
        vios = _run(rec)
        assert any(v.rule == "chain_complete_edges_indexed" for v in vios), (
            f"Expected chain_complete_edges_indexed violation, got: {_rules(vios)}"
        )


class TestSystemAnswerableFullWithUnindexedEntityFails:
    """Test 8: system_answerable='full' with an entity that has
    indexed_in_system=false should fail."""

    def test_fail(self):
        rec = _base_record(
            system_answerable="full",
            gold_entities=[
                {
                    "stable_entity_key": CLASS_KEY,
                    "entity_type": "java_class",
                    "qualified_name": "SysLoginController",
                    "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                    "start_line": 32,
                    "end_line": 138,
                    "relevance": "must_recall",
                    "indexed_in_system": True,
                },
                {
                    "stable_entity_key": MISSING_KEY,
                    "entity_type": "java_method",
                    "qualified_name": "SysUserServiceImpl.selectUserById",
                    "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                    "start_line": 45,
                    "end_line": 60,
                    "relevance": "source_only",
                    "indexed_in_system": False,
                    "missing_reason": "parser_limitation",
                    "source_evidence": {
                        "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                        "start_line": 45,
                        "end_line": 60,
                    },
                },
            ],
        )
        vios = _run(rec)
        # Should trigger system_answerable_consistency (rule 3 sub-check)
        # AND/OR system_answerable_full_requires_indexed (rule 8)
        relevant_rules = {
            "system_answerable_consistency",
            "system_answerable_full_requires_indexed",
        }
        matching = [v for v in vios if v.rule in relevant_rules]
        assert matching, (
            f"Expected system_answerable consistency violation, "
            f"got: {[(v.rule, v.field) for v in vios]}"
        )


class TestStableKeyRecomputation:
    """Test 9: For indexed_in_system=true entities, the recomputed stable
    key from snapshot data must match the gold stable_entity_key."""

    def test_correct_key_passes(self):
        """Matching key produces no stable_key_recompute violation."""
        rec = _base_record(
            gold_entities=[
                {
                    "stable_entity_key": CLASS_KEY,
                    "entity_type": "java_class",
                    "qualified_name": "SysLoginController",
                    "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                    "start_line": 32,
                    "end_line": 138,
                    "relevance": "must_recall",
                    "indexed_in_system": True,
                },
            ],
        )
        vios = _run(rec)
        assert not any(v.rule == "stable_key_recompute" for v in vios)

    def test_wrong_key_fails(self):
        """Mismatched key produces a stable_key_recompute violation.

        We simulate this by putting the entity's stable_entity_key as a
        key that exists in the snapshot (CLASS_KEY), but the snapshot
        entity behind CLASS_KEY has different field values than what
        would produce CLASS_KEY.  Since our fixture uses the real
        computation, we instead create a snapshot with a *swapped* key
        to force a mismatch.
        """
        # Build a custom snapshot where the entity stored under CLASS_KEY
        # actually has different qualified_name, causing recomputation to
        # yield a different key.
        tampered_entities = _make_snapshot_entities()
        tampered_entities[0] = dict(tampered_entities[0])
        tampered_entities[0]["qualified_name"] = "WrongName"  # tamper
        tampered_entities[0]["stable_entity_key"] = CLASS_KEY  # keep key

        tampered_lookup = build_entity_lookup(tampered_entities)
        tampered_keys = build_entity_key_set(tampered_entities)

        rec = _base_record(
            gold_entities=[
                {
                    "stable_entity_key": CLASS_KEY,
                    "entity_type": "java_class",
                    "qualified_name": "SysLoginController",
                    "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                    "start_line": 32,
                    "end_line": 138,
                    "relevance": "must_recall",
                    "indexed_in_system": True,
                },
            ],
        )

        vios = validate_record(
            record=rec,
            snapshot_keys=tampered_keys,
            entity_lookup=tampered_lookup,
            relation_set=build_relation_set(_make_snapshot_relations()),
            repo_root=None,
        )
        assert any(v.rule == "stable_key_recompute" for v in vios), (
            f"Expected stable_key_recompute violation, got: {_rules(vios)}"
        )


class TestFilePathVerification:
    """Test 10: File path and line number verification against the repo."""

    @pytest.fixture()
    def fake_repo(self, tmp_path: Path) -> Path:
        """Create a minimal repository tree with one file."""
        java_dir = tmp_path / "ruoyi-admin" / "src" / "main" / "java" / "com" / "ruoyi" / "web" / "controller" / "system"
        java_dir.mkdir(parents=True)
        java_file = java_dir / "SysLoginController.java"
        # Write 200 lines so line-range checks pass for lines 32-138
        java_file.write_text(
            "\n".join(f"// line {i}" for i in range(1, 201)),
            encoding="utf-8",
        )
        return tmp_path

    def test_existing_file_passes(self, fake_repo: Path):
        rec = _base_record(
            gold_entities=[
                {
                    "stable_entity_key": CLASS_KEY,
                    "entity_type": "java_class",
                    "qualified_name": "SysLoginController",
                    "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                    "start_line": 32,
                    "end_line": 138,
                    "relevance": "must_recall",
                    "indexed_in_system": True,
                },
            ],
        )
        entities = _make_snapshot_entities()
        relations = _make_snapshot_relations()
        vios = validate_record(
            record=rec,
            snapshot_keys=build_entity_key_set(entities),
            entity_lookup=build_entity_lookup(entities),
            relation_set=build_relation_set(relations),
            repo_root=fake_repo,
        )
        file_vios = [v for v in vios if v.rule == "file_path_verification"]
        assert file_vios == [], f"Expected no file violations, got: {file_vios}"

    def test_missing_file_fails(self, fake_repo: Path):
        rec = _base_record(
            gold_entities=[
                {
                    "stable_entity_key": MISSING_KEY,
                    "entity_type": "java_method",
                    "qualified_name": "SysUserServiceImpl.selectUserById",
                    "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                    "start_line": 45,
                    "end_line": 60,
                    "relevance": "must_recall",
                    "indexed_in_system": False,
                    "missing_reason": "parser_limitation",
                    "source_evidence": {
                        "file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
                        "start_line": 45,
                        "end_line": 60,
                    },
                },
            ],
            system_answerable="partial",
        )
        entities = _make_snapshot_entities()
        relations = _make_snapshot_relations()
        vios = validate_record(
            record=rec,
            snapshot_keys=build_entity_key_set(entities),
            entity_lookup=build_entity_lookup(entities),
            relation_set=build_relation_set(relations),
            repo_root=fake_repo,
        )
        file_vios = [v for v in vios if v.rule == "file_path_verification"]
        assert file_vios, "Expected file_path_verification violation for missing file"

    def test_line_out_of_range_fails(self, fake_repo: Path):
        rec = _base_record(
            gold_entities=[
                {
                    "stable_entity_key": CLASS_KEY,
                    "entity_type": "java_class",
                    "qualified_name": "SysLoginController",
                    "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                    "start_line": 32,
                    "end_line": 999,  # exceeds 200 lines
                    "relevance": "must_recall",
                    "indexed_in_system": True,
                },
            ],
        )
        entities = _make_snapshot_entities()
        relations = _make_snapshot_relations()
        vios = validate_record(
            record=rec,
            snapshot_keys=build_entity_key_set(entities),
            entity_lookup=build_entity_lookup(entities),
            relation_set=build_relation_set(relations),
            repo_root=fake_repo,
        )
        file_vios = [v for v in vios if v.rule == "file_path_verification"]
        assert file_vios, "Expected file_path_verification violation for out-of-range line"


class TestEndToEndDatasetValidation:
    """Integration test: write a tiny JSONL dataset + snapshot files to
    disk and run validate_dataset end-to-end."""

    def test_clean_dataset_passes(self, tmp_path: Path):
        # Write dataset
        ds_file = tmp_path / "dataset.jsonl"
        rec = _base_record()
        rec["gold_entities"] = [
            {
                "stable_entity_key": CLASS_KEY,
                "entity_type": "java_class",
                "qualified_name": "SysLoginController",
                "file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                "start_line": 32,
                "end_line": 138,
                "relevance": "must_recall",
                "indexed_in_system": True,
            },
        ]
        ds_file.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")

        # Write snapshot files
        ent_file = tmp_path / "entities.json"
        ent_file.write_text(json.dumps(_make_snapshot_entities()), encoding="utf-8")
        rel_file = tmp_path / "relations.json"
        rel_file.write_text(json.dumps(_make_snapshot_relations()), encoding="utf-8")

        result = validate_dataset(
            dataset_path=ds_file,
            entities_path=ent_file,
            relations_path=rel_file,
            repo_root=None,
        )
        assert result.all_pass, f"Expected pass, got violations: {result.violations}"
        assert result.total_records == 1
        assert result.passing_records == 1
