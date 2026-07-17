#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate a JSONL evaluation dataset file.

Performs two layers of validation:
  1. JSON Schema validation (structural) -- each line is checked against the
     evaluation case schema.
  2. Semantic validation -- cross-field and cross-record rules from SPEC.md
     Section 9.3 that cannot be expressed in JSON Schema Draft-07.

Usage:
    python validate_dataset.py [--schema PATH] DATASET_PATH

Exit codes:
    0  All records pass both validation layers.
    1  One or more records fail validation.

Examples:
    python validate_dataset.py evaluation/datasets/pilot.jsonl
    python validate_dataset.py --schema evaluation/schema/evaluation_case.schema.json evaluation/datasets/pilot.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional jsonschema import -- fall back to built-in checks when unavailable
# ---------------------------------------------------------------------------
try:
    import jsonschema  # type: ignore[import-untyped]
    import jsonschema.validators  # type: ignore[import-untyped]

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


# ===================================================================
# Error collector
# ===================================================================
class ValidationError:
    """A single validation error with full context."""

    __slots__ = ("question_id", "line_number", "field", "rule", "reason")

    def __init__(
        self,
        question_id: str,
        line_number: int,
        field: str,
        rule: str,
        reason: str,
    ) -> None:
        self.question_id = question_id
        self.line_number = line_number
        self.field = field
        self.rule = rule
        self.reason = reason

    def __str__(self) -> str:
        return (
            f"[line {self.line_number}] question_id={self.question_id}  "
            f"field={self.field}  rule={self.rule}  reason={self.reason}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "line_number": self.line_number,
            "field": self.field,
            "rule": self.rule,
            "reason": self.reason,
        }


# ===================================================================
# Fallback schema validator (used when jsonschema is not installed)
# ===================================================================

# Maps JSON Schema "type" keywords to Python types.
_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def _check_type(value: Any, expected_type: str) -> bool:
    """Check if *value* matches the JSON Schema *expected_type*."""
    py_types = _TYPE_MAP.get(expected_type)
    if py_types is None:
        return True  # unknown type keyword -- skip
    # In JSON, booleans are not integers even though Python bool is int subclass
    if expected_type == "integer" and isinstance(value, bool):
        return False
    if expected_type == "number" and isinstance(value, bool):
        return False
    return isinstance(value, py_types)


def _validate_instance_fallback(
    instance: Any,
    schema: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    """Recursively validate *instance* against *schema* without jsonschema.

    This is intentionally simpler than a full Draft-07 validator but covers
    the structural checks that matter for evaluation datasets: required
    fields, type checks, enum, pattern, minimum/maximum, minLength/maxLength,
    and additionalProperties.
    """
    # --- type ---
    if "type" in schema:
        expected = schema["type"]
        if not _check_type(instance, expected):
            errors.append(f"{path}: expected type '{expected}', got {type(instance).__name__}")
            return  # no point descending further

    # --- enum ---
    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append(
                f"{path}: value {instance!r} not in allowed values {schema['enum']}"
            )

    # --- string constraints ---
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(
                f"{path}: string length {len(instance)} < minLength {schema['minLength']}"
            )
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(
                f"{path}: string length {len(instance)} > maxLength {schema['maxLength']}"
            )
        if "pattern" in schema:
            if not re.search(schema["pattern"], instance):
                errors.append(
                    f"{path}: value {instance!r} does not match pattern '{schema['pattern']}'"
                )

    # --- integer/number constraints ---
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: value {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: value {instance} > maximum {schema['maximum']}")

    # --- object ---
    if isinstance(instance, dict):
        # required
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")

        properties = schema.get("properties", {})
        for key, sub_schema in properties.items():
            if key in instance:
                _validate_instance_fallback(
                    instance[key],
                    sub_schema,
                    f"{path}.{key}" if path else key,
                    errors,
                )

        # additionalProperties
        if schema.get("additionalProperties") is False:
            allowed = set(properties.keys())
            for key in instance:
                if key not in allowed:
                    errors.append(f"{path}: unexpected property '{key}'")

    # --- array ---
    if isinstance(instance, list) and "items" in schema:
        item_schema = schema["items"]
        for idx, item in enumerate(instance):
            _validate_instance_fallback(
                item, item_schema, f"{path}[{idx}]", errors
            )


def schema_validate_fallback(
    record: dict[str, Any], schema: dict[str, Any]
) -> list[str]:
    """Validate a single record using the built-in fallback validator.

    Returns a list of human-readable error strings.
    """
    errors: list[str] = []
    _validate_instance_fallback(record, schema, "", errors)
    return errors


def schema_validate_jsonschema(
    record: dict[str, Any], schema: dict[str, Any]
) -> list[str]:
    """Validate a single record using the ``jsonschema`` library.

    Returns a list of human-readable error strings.
    """
    errors: list[str] = []
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)
    for error in sorted(validator.iter_errors(record), key=lambda e: list(e.path)):
        path_str = ".".join(str(p) for p in error.absolute_path) or "<root>"
        errors.append(f"{path_str}: {error.message}")
    return errors


# ===================================================================
# Semantic validation rules (SPEC.md Section 9.3)
# ===================================================================

# Hex pattern for stable_entity_key (SHA-256 hex digest = 64 lowercase hex chars)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

# CJK Unified Ideographs range (common Chinese characters)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# CamelCase proper nouns (e.g. SysUserController, HashMap)
_CAMEL_CASE_RE = re.compile(r"[A-Z][a-z]+(?:[A-Z][a-z0-9]*)+")
# API paths (e.g. /api/users/list, /system/role)
_API_PATH_RE = re.compile(r"/[a-zA-Z0-9_/.@:-]+")
# Backtick-wrapped code (e.g. `some_code`)
_BACKTICK_RE = re.compile(r"`[^`]*`")


def _rule_trace_chain_gold(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 1: TRACE_CHAIN + source_answerable=true + system_answerable != insufficient
    must have gold_nodes and gold_edges."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    source_ans = record.get("source_answerable")
    sys_ans = record.get("system_answerable")
    if (
        record.get("task_type") == "TRACE_CHAIN"
        and source_ans is True
        and sys_ans in ("full", "partial")
    ):
        nodes = record.get("gold_nodes") or []
        edges = record.get("gold_edges") or []
        if len(nodes) == 0:
            errors.append(
                ValidationError(
                    qid, line_number, "gold_nodes",
                    "task_specific_gold",
                    "TRACE_CHAIN with source_answerable=true and "
                    "system_answerable != 'insufficient' must have non-empty gold_nodes",
                )
            )
        if len(edges) == 0:
            errors.append(
                ValidationError(
                    qid, line_number, "gold_edges",
                    "task_specific_gold",
                    "TRACE_CHAIN with source_answerable=true and "
                    "system_answerable != 'insufficient' must have non-empty gold_edges",
                )
            )
    return errors


def _rule_retrieval_coverage(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 2: retrieval layer requires at least one must_recall entity
    when source_answerable=true and system_answerable != 'insufficient'."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    layers = record.get("evaluation_layers") or []
    source_ans = record.get("source_answerable")
    sys_ans = record.get("system_answerable")
    if "retrieval" in layers and source_ans is True and sys_ans in ("full", "partial"):
        entities = record.get("gold_entities") or []
        has_must_recall = False
        for e in entities:
            if isinstance(e, dict) and e.get("relevance") == "must_recall":
                has_must_recall = True
                break
        if not has_must_recall:
            errors.append(
                ValidationError(
                    qid, line_number, "gold_entities",
                    "retrieval_entity_coverage",
                    "evaluation_layers includes 'retrieval' but no must_recall "
                    "entity found and source_answerable is not false",
                )
            )
    return errors


def _rule_line_range_validity(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 3: start_line <= end_line in gold_entities, evidence_ranges, gold_nodes."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")

    # gold_entities -- non-dict items are caught by schema validation
    for idx, entity in enumerate(record.get("gold_entities") or []):
        if not isinstance(entity, dict):
            continue
        start = entity.get("start_line")
        end = entity.get("end_line")
        if start is not None and end is not None and start > end:
            errors.append(
                ValidationError(
                    qid, line_number, f"gold_entities[{idx}]",
                    "line_range_validity",
                    f"start_line ({start}) > end_line ({end})",
                )
            )

    # gold_nodes -- non-dict items are caught by schema validation
    for idx, node in enumerate(record.get("gold_nodes") or []):
        if not isinstance(node, dict):
            continue
        start = node.get("start_line")
        end = node.get("end_line")
        if start is not None and end is not None and start > end:
            errors.append(
                ValidationError(
                    qid, line_number, f"gold_nodes[{idx}]",
                    "line_range_validity",
                    f"start_line ({start}) > end_line ({end})",
                )
            )

    # evidence_ranges inside required_claims -- non-dict items caught by schema
    for ci, claim in enumerate(record.get("required_claims") or []):
        if not isinstance(claim, dict):
            continue
        for ri, er in enumerate(claim.get("evidence_ranges") or []):
            start = er.get("start_line")
            end = er.get("end_line")
            if start is not None and end is not None and start > end:
                errors.append(
                    ValidationError(
                        qid, line_number,
                        f"required_claims[{ci}].evidence_ranges[{ri}]",
                        "line_range_validity",
                        f"start_line ({start}) > end_line ({end})",
                    )
                )

    return errors


def _rule_edge_endpoint_existence(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 4: gold_edges source_key/target_key must exist in gold_nodes stable_entity_keys."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    nodes = record.get("gold_nodes") or []
    edges = record.get("gold_edges") or []
    if not edges:
        return errors

    node_keys = {
        n.get("stable_entity_key") for n in nodes
        if isinstance(n, dict) and n.get("stable_entity_key")
    }

    for idx, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        src = edge.get("source_key")
        tgt = edge.get("target_key")
        if src and src not in node_keys:
            errors.append(
                ValidationError(
                    qid, line_number, f"gold_edges[{idx}].source_key",
                    "edge_endpoint_existence",
                    f"source_key '{src}' not found in gold_nodes stable_entity_keys",
                )
            )
        if tgt and tgt not in node_keys:
            errors.append(
                ValidationError(
                    qid, line_number, f"gold_edges[{idx}].target_key",
                    "edge_endpoint_existence",
                    f"target_key '{tgt}' not found in gold_nodes stable_entity_keys",
                )
            )
    return errors


def _rule_annotator_reviewer_separation(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 5: annotation.annotator must not equal annotation.reviewer."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    annotation = record.get("annotation") or {}
    annotator = annotation.get("annotator")
    reviewer = annotation.get("reviewer")
    if annotator and reviewer and annotator == reviewer:
        errors.append(
            ValidationError(
                qid, line_number, "annotation",
                "annotator_reviewer_separation",
                f"annotator and reviewer are both '{annotator}'; they must differ",
            )
        )
    return errors


def _rule_answerable_uncertainties(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 9: source_answerable=false must have non-empty expected_uncertainties."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    if record.get("source_answerable") is False:
        uncertainties = record.get("expected_uncertainties") or []
        if len(uncertainties) == 0:
            errors.append(
                ValidationError(
                    qid, line_number, "expected_uncertainties",
                    "answerable_uncertainties",
                    "source_answerable=false but expected_uncertainties is empty or missing",
                )
            )
    return errors


def _rule_status_metric_exclusion(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 8: rejected/needs_review must not have machine_verified/human_verified gold_status."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    annotation = record.get("annotation") or {}
    review_status = annotation.get("review_status", "")
    gold_status = record.get("gold_status", "")
    if review_status in ("rejected", "needs_review") and gold_status in (
        "machine_verified",
        "human_verified",
    ):
        errors.append(
            ValidationError(
                qid, line_number, "gold_status",
                "status_metric_exclusion",
                f"review_status='{review_status}' but gold_status='{gold_status}'; "
                "rejected/needs_review samples must not be machine_verified or human_verified",
            )
        )
    return errors


def _rule_provenance_coverage(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 10: provenance.source_files must cover all files in gold_nodes and gold_entities."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    provenance = record.get("provenance") or {}
    source_files = set(provenance.get("source_files") or [])
    if not source_files:
        # No provenance source_files at all -- only flag if there are gold refs
        pass

    referenced_files: set[str] = set()

    for entity in record.get("gold_entities") or []:
        if not isinstance(entity, dict):
            continue
        fp = entity.get("file_path")
        if fp:
            referenced_files.add(fp)

    for node in record.get("gold_nodes") or []:
        if not isinstance(node, dict):
            continue
        fp = node.get("file_path")
        if fp:
            referenced_files.add(fp)

    missing = referenced_files - source_files
    if missing:
        errors.append(
            ValidationError(
                qid, line_number, "provenance.source_files",
                "provenance_coverage",
                f"files referenced in gold evidence but missing from "
                f"provenance.source_files: {sorted(missing)}",
            )
        )
    return errors


# ===================================================================
# New Schema v1.2.0 semantic rules
# ===================================================================


def _rule_entity_stable_key_format(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 11: gold_entities items must have stable_entity_key as 64-char hex string."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    for idx, entity in enumerate(record.get("gold_entities") or []):
        if not isinstance(entity, dict):
            continue
        sek = entity.get("stable_entity_key")
        if not sek or not isinstance(sek, str) or not _HEX64_RE.match(sek):
            errors.append(
                ValidationError(
                    qid, line_number, f"gold_entities[{idx}].stable_entity_key",
                    "entity_stable_key_format",
                    f"stable_entity_key must be a 64-char lowercase hex string, "
                    f"got {sek!r}",
                )
            )
    return errors


def _rule_edge_indexed_chain_complete(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 12: gold_edges with indexed_in_system=false requires chain_complete=false."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    edges = record.get("gold_edges") or []
    has_unindexed = any(
        isinstance(e, dict) and e.get("indexed_in_system") is False
        for e in edges
    )
    if has_unindexed and record.get("chain_complete") is not False:
        errors.append(
            ValidationError(
                qid, line_number, "chain_complete",
                "edge_indexed_chain_complete",
                "gold_edges with indexed_in_system=false requires "
                "chain_complete=false on the parent record",
            )
        )
    return errors


def _rule_partial_answerable_requires_unindexed_edge(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 13: system_answerable='partial' requires at least one gold_edge
    with indexed_in_system=false."""
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    if record.get("system_answerable") == "partial":
        edges = record.get("gold_edges") or []
        has_unindexed = any(
            isinstance(e, dict) and e.get("indexed_in_system") is False
            for e in edges
        )
        if not has_unindexed:
            errors.append(
                ValidationError(
                    qid, line_number, "system_answerable",
                    "partial_answerable_requires_unindexed_edge",
                    "system_answerable='partial' requires at least one gold_edge "
                    "with indexed_in_system=false",
                )
            )
    return errors


def _rule_language_consistency(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 14: question text should be consistent with the declared language.

    This is a LOW-CONFIDENCE check -- only obvious mismatches are flagged.
    Proper nouns (CamelCase identifiers), API paths, and backtick-wrapped
    code tokens are stripped before counting so they do not skew the
    CJK-vs-Latin ratio.
    """
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    language = record.get("language", "")
    question = record.get("question", "")

    if not question or not language:
        return errors

    # Strip tokens that are language-neutral: proper nouns, API paths, code.
    cleaned = _BACKTICK_RE.sub("", question)
    cleaned = _CAMEL_CASE_RE.sub("", cleaned)
    cleaned = _API_PATH_RE.sub("", cleaned)

    cjk_count = len(_CJK_RE.findall(cleaned))

    # Non-whitespace character count for ratio calculation.
    non_ws = re.sub(r"\s+", "", cleaned)
    non_ws_count = len(non_ws)

    if language == "zh":
        # Chinese questions should contain at least 3 CJK characters.
        if cjk_count < 3:
            errors.append(
                ValidationError(
                    qid, line_number, "question",
                    "language_consistency",
                    f"language='zh' but only {cjk_count} CJK character(s) "
                    f"found in question text",
                )
            )
    elif language == "en":
        # English questions should not have CJK as the majority.
        if non_ws_count > 0 and cjk_count / non_ws_count > 0.5:
            pct = round(cjk_count * 100 / non_ws_count)
            errors.append(
                ValidationError(
                    qid, line_number, "question",
                    "language_consistency",
                    f"language='en' but CJK characters constitute {pct}% "
                    f"({cjk_count}/{non_ws_count}) of non-whitespace content",
                )
            )

    return errors


def _rule_execution_status_gold_consistency(
    record: dict[str, Any], line_number: int
) -> list[ValidationError]:
    """Rule 15: prepared_not_executed records must not have verified gold_status.

    If a record was never executed against the codebase, its gold standard
    cannot logically be ``machine_verified`` or ``human_verified``.
    """
    errors: list[ValidationError] = []
    qid = record.get("question_id", "<unknown>")
    exec_status = record.get("execution_status", "")
    gold_status = record.get("gold_status", "")

    if exec_status == "prepared_not_executed" and gold_status in (
        "machine_verified",
        "human_verified",
    ):
        errors.append(
            ValidationError(
                qid, line_number, "gold_status",
                "execution_status_gold_consistency",
                f"execution_status='prepared_not_executed' but "
                f"gold_status='{gold_status}'; gold cannot be verified "
                f"if the record was not executed",
            )
        )

    return errors


# Per-record semantic validators
_PER_RECORD_RULES = [
    _rule_trace_chain_gold,
    _rule_retrieval_coverage,
    _rule_line_range_validity,
    _rule_edge_endpoint_existence,
    _rule_annotator_reviewer_separation,
    _rule_answerable_uncertainties,
    _rule_status_metric_exclusion,
    _rule_provenance_coverage,
    _rule_entity_stable_key_format,
    _rule_edge_indexed_chain_complete,
    _rule_partial_answerable_requires_unindexed_edge,
    _rule_language_consistency,
    _rule_execution_status_gold_consistency,
]


# ===================================================================
# Cross-record semantic rules
# ===================================================================


def _cross_record_rules(
    records: list[tuple[int, dict[str, Any]]],
) -> list[ValidationError]:
    """Validate rules that span multiple records.

    Rule 6: question_fingerprint uniqueness within the dataset.
    Rule 7: same fingerprint must not appear in different splits.
    """
    errors: list[ValidationError] = []

    # Rule 6 -- fingerprint uniqueness
    fingerprint_lines: dict[str, list[tuple[int, str]]] = {}
    for line_number, rec in records:
        fp = rec.get("question_fingerprint", "")
        qid = rec.get("question_id", "<unknown>")
        if fp:
            fingerprint_lines.setdefault(fp, []).append((line_number, qid))

    for fp, occurrences in fingerprint_lines.items():
        if len(occurrences) > 1:
            lines = ", ".join(str(ln) for ln, _ in occurrences)
            qids = ", ".join(qid for _, qid in occurrences)
            # Report on every duplicate occurrence
            for line_number, qid in occurrences:
                errors.append(
                    ValidationError(
                        qid, line_number, "question_fingerprint",
                        "question_fingerprint_uniqueness",
                        f"duplicate fingerprint '{fp}' found on lines {lines} "
                        f"(question_ids: {qids})",
                    )
                )

    # Rule 7 -- split fingerprint uniqueness
    fingerprint_splits: dict[str, list[tuple[int, str, str]]] = {}
    for line_number, rec in records:
        fp = rec.get("question_fingerprint", "")
        qid = rec.get("question_id", "<unknown>")
        split = rec.get("split", "")
        if fp and split:
            fingerprint_splits.setdefault(fp, []).append(
                (line_number, qid, split)
            )

    for fp, occurrences in fingerprint_splits.items():
        splits_seen = {s for _, _, s in occurrences}
        if len(splits_seen) > 1:
            detail = "; ".join(
                f"line {ln} ({qid}, split={s})" for ln, qid, s in occurrences
            )
            for line_number, qid, split in occurrences:
                errors.append(
                    ValidationError(
                        qid, line_number, "question_fingerprint",
                        "split_fingerprint_uniqueness",
                        f"fingerprint '{fp}' appears in multiple splits "
                        f"({sorted(splits_seen)}): {detail}",
                    )
                )

    return errors


# ===================================================================
# Main validation pipeline
# ===================================================================


def load_schema(schema_path: str) -> dict[str, Any]:
    """Load and return the JSON Schema from *schema_path*."""
    with open(schema_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_dataset(dataset_path: str) -> list[tuple[int, dict[str, Any]]]:
    """Load a JSONL dataset file.

    Returns a list of ``(line_number, record)`` tuples.  Blank lines are
    skipped.  JSON parse errors are returned as special error records with
    a ``_parse_error`` key.
    """
    records: list[tuple[int, dict[str, Any]]] = []
    with open(dataset_path, "r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                record = {"_parse_error": str(exc), "_line_number": line_number}
            records.append((line_number, record))
    return records


def validate_dataset(
    dataset_path: str,
    schema_path: str | None = None,
) -> tuple[list[ValidationError], int]:
    """Run full validation on a JSONL dataset.

    Returns ``(errors, total_record_count)``.
    """
    # Determine schema path
    if schema_path is None:
        # Default: look relative to this script
        script_dir = Path(__file__).resolve().parent
        schema_path = str(
            script_dir.parent / "schema" / "evaluation_case.schema.json"
        )

    schema = load_schema(schema_path)
    records = load_dataset(dataset_path)

    all_errors: list[ValidationError] = []

    # --- Phase 1: per-record validation ---
    valid_records: list[tuple[int, dict[str, Any]]] = []
    for line_number, record in records:
        qid = record.get("question_id", "<unknown>")

        # Handle JSON parse errors
        if "_parse_error" in record:
            all_errors.append(
                ValidationError(
                    qid, line_number, "<json>",
                    "json_parse",
                    f"failed to parse JSON: {record['_parse_error']}",
                )
            )
            continue

        # Schema validation
        if HAS_JSONSCHEMA:
            schema_errors = schema_validate_jsonschema(record, schema)
        else:
            schema_errors = schema_validate_fallback(record, schema)

        for msg in schema_errors:
            # Extract field path from the error message prefix
            field = msg.split(":")[0] if ":" in msg else "<root>"
            reason = msg.split(":", 1)[1].strip() if ":" in msg else msg
            all_errors.append(
                ValidationError(
                    qid, line_number, field,
                    "json_schema",
                    reason,
                )
            )

        # Semantic validation (run even if schema errors exist, to gather
        # as many errors as possible in one pass)
        for rule_fn in _PER_RECORD_RULES:
            all_errors.extend(rule_fn(record, line_number))

        valid_records.append((line_number, record))

    # --- Phase 2: cross-record validation ---
    all_errors.extend(_cross_record_rules(valid_records))

    return all_errors, len(records)


# ===================================================================
# CLI
# ===================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a JSONL evaluation dataset against the evaluation case "
            "schema and semantic rules from SPEC.md Section 9.3."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  All records pass.\n"
            "  1  One or more records fail validation.\n"
        ),
    )
    parser.add_argument(
        "dataset_path",
        help="Path to the JSONL evaluation dataset file.",
    )
    parser.add_argument(
        "--schema",
        dest="schema_path",
        default=None,
        help=(
            "Path to the JSON Schema file. "
            "Defaults to evaluation/schema/evaluation_case.schema.json "
            "relative to this script."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    dataset_path: str = args.dataset_path
    schema_path: str | None = args.schema_path

    if not os.path.isfile(dataset_path):
        print(f"Error: dataset file not found: {dataset_path}", file=sys.stderr)
        return 1

    if schema_path and not os.path.isfile(schema_path):
        print(f"Error: schema file not found: {schema_path}", file=sys.stderr)
        return 1

    # Check jsonschema availability
    if not HAS_JSONSCHEMA:
        print(
            "Note: 'jsonschema' package not installed; using built-in structural "
            "validator (covers required fields, types, enums, patterns, and "
            "additionalProperties).",
            file=sys.stderr,
        )

    errors, total = validate_dataset(dataset_path, schema_path)

    # --- Report ---
    if errors:
        for err in errors:
            print(str(err))
        print()

    # Compute error categories
    structural_errors = sum(1 for e in errors if e.rule == "json_schema")
    semantic_errors = len(errors) - structural_errors

    # Compute pass/fail counts per record (by line number)
    error_lines: set[int] = set()
    for err in errors:
        error_lines.add(err.line_number)
    passed = total - len(error_lines)
    failed = len(error_lines)

    print(
        f"Summary: {total} total records, "
        f"{structural_errors} structural error(s), "
        f"{semantic_errors} semantic error(s), "
        f"{passed} passed, {failed} failed, "
        f"{len(errors)} total error(s)"
    )

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
