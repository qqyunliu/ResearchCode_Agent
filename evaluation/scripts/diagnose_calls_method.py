"""Diagnose why CALLS_METHOD relations are zero for the RuoYi-Vue scan.

This script parses real controller files from the RuoYi-Vue workspace and
traces the data through the parser and relation builder to identify exactly
where the CALLS_METHOD pipeline breaks down.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Allow running from evaluation/scripts without installing the backend package.
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from app.parsers.java_parser import JavaParser
from app.parsers.relation_builder import build_relations, _append_method_calls
from app.parsers.base import EntityCandidate, RelationCandidate


WORKSPACE = Path(__file__).resolve().parents[1] / "workspaces" / "ruoyi-vue"

# All Java controller files that should produce CALLS_METHOD edges.
CONTROLLER_FILES = [
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java",
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysMenuController.java",
]


def parse_file(parser: JavaParser, rel_path: str) -> tuple[list[EntityCandidate], list[RelationCandidate]]:
    full_path = WORKSPACE / rel_path
    source = full_path.read_text(encoding="utf-8")
    result = parser.parse(rel_path, source)
    return list(result.entities), list(result.relations)


def print_section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def diagnose_single_file(parser: JavaParser, rel_path: str) -> None:
    """Parse one controller and print detailed extraction data."""
    print_section(f"DIAGNOSIS: {rel_path}")

    entities, relations = parse_file(parser, rel_path)

    # 1. Class entities
    classes = [e for e in entities if e.entity_type == "java_class"]
    print(f"\n--- Classes ({len(classes)}) ---")
    for cls in classes:
        is_ctrl = cls.metadata.get("is_controller")
        is_svc = cls.metadata.get("is_service")
        print(f"  {cls.qualified_name}  controller={is_ctrl}  service={is_svc}")

    # 2. Method entities and their invocations
    methods = [e for e in entities if e.entity_type == "java_method"]
    print(f"\n--- Methods ({len(methods)}) ---")
    total_invocations = 0
    methods_with_invocations = 0
    for method in methods:
        invocations = method.metadata.get("invocations", [])
        declaring_class = method.metadata.get("declaring_class", "?")
        inv_count = len(invocations) if isinstance(invocations, list) else 0
        if inv_count > 0:
            methods_with_invocations += 1
            total_invocations += inv_count
        print(f"  {method.qualified_name}  (class={declaring_class})  invocations={inv_count}")
        if isinstance(invocations, list):
            for inv in invocations:
                print(f"    -> {inv.get('qualifier', '?')}.{inv.get('method', '?')}()"
                      f"  [receiver_type={inv.get('receiver_type', 'NONE')}]")

    print(f"\n  Summary: {methods_with_invocations}/{len(methods)} methods have invocations,"
          f" {total_invocations} total invocations")

    # 3. Parser relations (CONTAINS, DEFINES_API)
    print(f"\n--- Parser Relations ({len(relations)}) ---")
    for rel in relations:
        print(f"  {rel.relation_type}: {rel.source_key[:60]}... -> {rel.target_key[:60]}...")


def diagnose_full_pipeline(parser: JavaParser) -> None:
    """Parse all files in the project and run the full relation builder."""
    print_section("FULL PIPELINE DIAGNOSIS")

    # Collect ALL Java files, not just controllers
    all_java_files = sorted(WORKSPACE.rglob("*.java"))
    print(f"\nTotal Java files found: {len(all_java_files)}")

    all_entities: list[EntityCandidate] = []
    all_parser_relations: list[RelationCandidate] = []

    for java_file in all_java_files:
        rel_path = java_file.relative_to(WORKSPACE).as_posix()
        try:
            source = java_file.read_text(encoding="utf-8")
            result = parser.parse(rel_path, source)
            # Apply namespacing like IndexService does
            prefix = f"{rel_path}::"
            for entity in result.entities:
                namespaced = EntityCandidate(
                    local_key=f"{prefix}{entity.local_key}",
                    entity_type=entity.entity_type,
                    name=entity.name,
                    qualified_name=entity.qualified_name,
                    file_path=entity.file_path,
                    start_line=entity.start_line,
                    end_line=entity.end_line,
                    content=entity.content,
                    metadata=entity.metadata,
                )
                all_entities.append(namespaced)
            for relation in result.relations:
                namespaced_rel = RelationCandidate(
                    source_key=f"{prefix}{relation.source_key}",
                    target_key=f"{prefix}{relation.target_key}",
                    relation_type=relation.relation_type,
                    confidence=relation.confidence,
                    metadata=relation.metadata,
                )
                all_parser_relations.append(namespaced_rel)
        except Exception as exc:
            print(f"  PARSE ERROR: {rel_path}: {exc}")

    print(f"Total entities parsed: {len(all_entities)}")
    print(f"Total parser relations: {len(all_parser_relations)}")

    # Entity type distribution
    type_counts = Counter(e.entity_type for e in all_entities)
    print("\nEntity type distribution:")
    for etype, count in type_counts.most_common():
        print(f"  {etype}: {count}")

    # --- SERVICE CLASS ANALYSIS ---
    print_section("SERVICE CLASS ANALYSIS")

    service_classes = {
        entity.qualified_name
        for entity in all_entities
        if (
            entity.entity_type == "java_class"
            and entity.metadata.get("is_service") is True
        )
    }
    print(f"\nClasses with is_service=True: {len(service_classes)}")
    for sc in sorted(service_classes):
        print(f"  {sc}")

    # Also check for @Component classes
    component_classes = {
        entity.qualified_name
        for entity in all_entities
        if (
            entity.entity_type == "java_class"
            and "Component" in entity.metadata.get("annotations", [])
        )
    }
    print(f"\nClasses with @Component (not @Service): {len(component_classes)}")
    for cc in sorted(component_classes - service_classes):
        print(f"  {cc}")

    # Build service aliases (same logic as relation_builder.py)
    service_aliases: dict[str, set[str]] = defaultdict(set)
    for class_name in service_classes:
        service_aliases[class_name].add(class_name)
        service_aliases[class_name.rsplit(".", 1)[-1]].add(class_name)

    print(f"\nService alias keys: {sorted(service_aliases.keys())}")

    # --- INVOCATION ANALYSIS ---
    print_section("INVOCATION ANALYSIS")

    # Collect all invocations from all methods
    all_invocations: list[dict] = []
    methods_with_inv = 0
    for entity in all_entities:
        if entity.entity_type != "java_method":
            continue
        invocations = entity.metadata.get("invocations", [])
        if not isinstance(invocations, list) or not invocations:
            continue
        methods_with_inv += 1
        for inv in invocations:
            all_invocations.append({
                **inv,
                "_source_method": entity.qualified_name,
                "_source_file": entity.file_path,
                "_declaring_class": entity.metadata.get("declaring_class"),
            })

    print(f"\nMethods with invocations: {methods_with_inv}")
    print(f"Total invocations found: {len(all_invocations)}")

    # Analyze receiver types
    receiver_types = Counter(inv.get("receiver_type") for inv in all_invocations)
    print(f"\nReceiver type distribution:")
    for rtype, count in receiver_types.most_common():
        in_aliases = rtype in service_aliases if rtype else False
        print(f"  {rtype}: {count} occurrences  (in service_aliases: {in_aliases})")

    # Check each invocation's resolution path
    print_section("INVOCATION RESOLUTION TRACE (first 30)")

    service_methods: list[EntityCandidate] = []
    for entity in all_entities:
        if entity.entity_type != "java_method":
            continue
        declaring_class = entity.metadata.get("declaring_class")
        if isinstance(declaring_class, str) and declaring_class in service_classes:
            service_methods.append(entity)

    methods_by_name: dict[str, list[EntityCandidate]] = defaultdict(list)
    methods_by_class_and_name: dict[tuple[str, str], list[EntityCandidate]] = defaultdict(list)
    for method in service_methods:
        declaring_class = method.metadata["declaring_class"]
        methods_by_name[method.name].append(method)
        methods_by_class_and_name[(str(declaring_class), method.name)].append(method)

    print(f"\nService methods indexed: {len(service_methods)}")
    print(f"Unique method names: {len(methods_by_name)}")

    resolved = 0
    unresolved_reasons: Counter = Counter()

    for i, inv in enumerate(all_invocations[:30]):
        method_name = inv.get("method")
        receiver_type = inv.get("receiver_type")
        qualifier = inv.get("qualifier")
        source = inv.get("_source_method")

        target = None
        confidence = 0.0
        reason = ""

        if isinstance(receiver_type, str):
            alias_set = service_aliases.get(receiver_type, set())
            candidates = [
                m
                for cn in alias_set
                for m in methods_by_class_and_name.get((cn, method_name), [])
            ]
            if len(candidates) == 1:
                target = candidates[0]
                confidence = 0.8
                reason = "receiver_type_match"
            elif len(candidates) == 0:
                reason = f"receiver_type '{receiver_type}' not in service_aliases"
            else:
                reason = f"receiver_type '{receiver_type}' -> {len(candidates)} candidates (ambiguous)"
        else:
            candidates = methods_by_name.get(method_name, [])
            if len(candidates) == 1:
                target = candidates[0]
                confidence = 0.6
                reason = "unique_method_name"
            elif len(candidates) == 0:
                reason = f"no receiver_type; method '{method_name}' not found by name"
            else:
                reason = f"no receiver_type; method '{method_name}' -> {len(candidates)} candidates (ambiguous)"

        status = "RESOLVED" if target else "FAILED"
        if target:
            resolved += 1
            print(f"  [{i+1:2d}] {status}: {source} -> {qualifier}.{method_name}()"
                  f"  receiver_type={receiver_type}  =>  {target.qualified_name} ({confidence})")
        else:
            unresolved_reasons[reason] += 1
            print(f"  [{i+1:2d}] {status}: {source} -> {qualifier}.{method_name}()"
                  f"  receiver_type={receiver_type}  REASON: {reason}")

    # Full resolution stats (all invocations)
    print_section("FULL RESOLUTION STATISTICS")
    total_resolved = 0
    total_unresolved = 0
    all_unresolved_reasons: Counter = Counter()

    for inv in all_invocations:
        method_name = inv.get("method")
        receiver_type = inv.get("receiver_type")

        target = None
        if isinstance(receiver_type, str):
            alias_set = service_aliases.get(receiver_type, set())
            candidates = [
                m
                for cn in alias_set
                for m in methods_by_class_and_name.get((cn, method_name), [])
            ]
            if len(candidates) == 1:
                target = candidates[0]
            elif len(candidates) == 0:
                all_unresolved_reasons[f"receiver_type_not_in_aliases:{receiver_type}"] += 1
            else:
                all_unresolved_reasons[f"ambiguous_receiver_type:{len(candidates)}_candidates"] += 1
        else:
            candidates = methods_by_name.get(method_name, [])
            if len(candidates) == 1:
                target = candidates[0]
            elif len(candidates) == 0:
                all_unresolved_reasons["method_name_not_found"] += 1
            else:
                all_unresolved_reasons[f"ambiguous_method_name:{len(candidates)}_candidates"] += 1

        if target:
            total_resolved += 1
        else:
            total_unresolved += 1

    print(f"\nTotal invocations: {len(all_invocations)}")
    print(f"Resolved to CALLS_METHOD: {total_resolved}")
    print(f"Unresolved (dropped): {total_unresolved}")
    print(f"\nUnresolved reason breakdown:")
    for reason, count in all_unresolved_reasons.most_common():
        print(f"  {reason}: {count}")

    # --- Run the actual build_relations ---
    print_section("ACTUAL build_relations() OUTPUT")
    relations = build_relations(all_entities, all_parser_relations)
    rel_type_counts = Counter(r.relation_type for r in relations)
    print(f"\nRelation type distribution:")
    for rtype, count in rel_type_counts.most_common():
        print(f"  {rtype}: {count}")

    calls_method = [r for r in relations if r.relation_type == "CALLS_METHOD"]
    print(f"\nCALLS_METHOD relations: {len(calls_method)}")
    for r in calls_method[:10]:
        print(f"  {r.source_key[:60]} -> {r.target_key[:60]}  conf={r.confidence}")


def main() -> None:
    parser = JavaParser()

    # Part 1: Detailed single-file diagnosis
    for rel_path in CONTROLLER_FILES:
        diagnose_single_file(parser, rel_path)

    # Part 2: Full pipeline
    diagnose_full_pipeline(parser)


if __name__ == "__main__":
    main()
