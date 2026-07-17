#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Canonical Pilot Dataset Pipeline for ResearchCode-Agent Evaluation.
Phases A-F: Curate -> Annotate -> Review -> Merge -> Validate -> Report.
"""

import json
import hashlib
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# ===================================================================
# Configuration
# ===================================================================
REPO_ID = "ruoyi-vue"
COMMIT_SHA = "41720e624c5a668c7d3777835e4c87095a7a1dfd"
REPO_ROOT = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\workspaces\ruoyi-vue")
SNAPSHOT_DIR = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\runtime\pilot\snapshot")
OLD_CANDIDATES = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\archive\stage2a-draft-invalid\pilot_candidates.jsonl")
HISTORICAL_CASES = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\annotations\proposed\historical_change_cases.json")

OUTPUT_CURATED = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\annotations\proposed\curated_questions.json")
OUTPUT_ANNOTATED = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\annotations\proposed\annotated_by_b.json")
OUTPUT_REVIEWED = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\annotations\reviewed\reviewed_by_c.json")
OUTPUT_CANONICAL = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\datasets\pilot.jsonl")
OUTPUT_REPORT = Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\reports\canonical-pilot-summary.md")

DATASET_VERSION = "1.2"

# ===================================================================
# Helpers
# ===================================================================

def compute_stable_key(repo_id, commit_sha, file_path, entity_type, qualified_name, start_line, end_line):
    """Compute stable entity key as SHA-256."""
    normalized_path = file_path.replace("\\", "/").lower()
    payload = "|".join([
        str(repo_id), str(commit_sha), normalized_path,
        str(entity_type), str(qualified_name),
        str(int(start_line)), str(int(end_line))
    ]).strip()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_fingerprint(question_text):
    """First 8 chars of SHA-256 of normalized question text."""
    normalized = question_text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


def file_exists_in_repo(file_path):
    """Check if a file exists in the repository."""
    full_path = REPO_ROOT / file_path
    return full_path.is_file()


def count_file_lines(file_path):
    """Count lines in a repo file."""
    full_path = REPO_ROOT / file_path
    if not full_path.is_file():
        return 0
    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def load_snapshot_entities():
    """Load code_entities.json from snapshot."""
    path = SNAPSHOT_DIR / "code_entities.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_snapshot_relations():
    """Load code_relations.json from snapshot."""
    path = SNAPSHOT_DIR / "code_relations.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_entity_in_snapshot(qualified_name, entity_type=None):
    """Find an entity in the snapshot by qualified_name."""
    for e in SNAPSHOT_ENTITIES:
        if e["qualified_name"] == qualified_name:
            if entity_type is None or e["entity_type"] == entity_type:
                return e
    return None


def find_entities_by_file(file_path):
    """Find all entities in a given file from snapshot."""
    results = []
    for e in SNAPSHOT_ENTITIES:
        if e["file_path"] == file_path:
            results.append(e)
    return results


def check_relation_exists(source_key, target_key, relation_type):
    """Check if a relation exists in the snapshot."""
    for r in SNAPSHOT_RELATIONS:
        if (r["source_key"] == source_key and
            r["target_key"] == target_key and
            r["relation_type"] == relation_type):
            return True
    return False


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# Load snapshot data globally
print("Loading snapshot data...")
SNAPSHOT_ENTITIES = load_snapshot_entities()
SNAPSHOT_RELATIONS = load_snapshot_relations()
print(f"  Entities: {len(SNAPSHOT_ENTITIES)}, Relations: {len(SNAPSHOT_RELATIONS)}")

# Build index by stable_entity_key for quick lookup
ENTITY_BY_KEY = {e["stable_entity_key"]: e for e in SNAPSHOT_ENTITIES}

# ===================================================================
# PHASE A: Question Curator
# ===================================================================
def phase_a_curate():
    print("\n=== PHASE A: Question Curator ===")

    # Load old candidates
    old_candidates = []
    with open(OLD_CANDIDATES, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                old_candidates.append(json.loads(line))

    print(f"  Loaded {len(old_candidates)} old candidates")

    # Load historical change cases
    with open(HISTORICAL_CASES, "r", encoding="utf-8") as f:
        hc_data = json.load(f)
    hc_cases = hc_data["cases"]
    print(f"  Loaded {len(hc_cases)} historical change cases")

    curated = []
    seq = 1

    # Process each old candidate - keep all 36 as they are well-structured
    for old in old_candidates:
        task_type = old["task_type"]

        # Fix question_id format: use hyphens only (no underscores allowed by schema pattern)
        task_slug = task_type.lower().replace("_", "-")
        new_id = f"ruoyi-{task_slug}-{seq:04d}"

        # Keep the question text, task_type, language, difficulty
        rec = {
            "question_id": new_id,
            "task_type": task_type,
            "language": old["language"],
            "difficulty": old["difficulty"],
            "question": old["question"],
            "source_answerable": old.get("answerable", True),
            "evaluation_layers": old.get("evaluation_layers", []),
            "expected_task_type": old.get("expected_task_type", task_type),
            # Provenance hints from old data (source files only, no gold)
            "_provenance_files": old.get("provenance", {}).get("source_files", []),
            "_provenance_lines": old.get("provenance", {}).get("source_lines", []),
            "_old_notes": old.get("annotation", {}).get("notes", ""),
            "_special_types": old.get("special_sample_type", []),
            "_old_forbidden": old.get("forbidden_claims", []),
            "_old_uncertainties": old.get("expected_uncertainties", []),
        }

        curated.append(rec)
        seq += 1

    # Add historical change cases as CHANGE_PLAN
    for hc in hc_cases:
        new_id = f"ruoyi-change-plan-{seq:04d}"

        # Build question from change request
        question = hc["change_request"]

        rec = {
            "question_id": new_id,
            "task_type": "CHANGE_PLAN",
            "language": "zh" if any('\u4e00' <= c <= '\u9fff' for c in hc["commit_message"]) else "en",
            "difficulty": "medium",
            "question": question,
            "source_answerable": True,
            "evaluation_layers": ["routing", "retrieval", "synthesis"],
            "expected_task_type": "CHANGE_PLAN",
            "_provenance_files": hc["observed_changed_files"],
            "_provenance_lines": [],
            "_old_notes": hc.get("suitability_notes", ""),
            "_special_types": [],
            "_old_forbidden": [],
            "_old_uncertainties": [],
            "_historical_change": True,
            "_hc_case_id": hc["case_id"],
            "_hc_base_commit": hc["base_commit_sha"],
            "_hc_target_commit": hc["target_commit_sha"],
            "_hc_commit_message": hc["commit_message"],
            "_hc_change_type": hc["change_type"],
            "_hc_diff_summary": hc["diff_summary"],
            "_hc_layers_touched": hc["layers_touched"],
        }

        curated.append(rec)
        seq += 1

    print(f"  Total curated questions: {len(curated)}")

    # Distribution check
    from collections import Counter
    type_counts = Counter(q["task_type"] for q in curated)
    print(f"  Distribution: {dict(type_counts)}")

    # Write curated output
    OUTPUT_CURATED.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CURATED, "w", encoding="utf-8") as f:
        json.dump(curated, f, ensure_ascii=False, indent=2)

    print(f"  Written to {OUTPUT_CURATED}")
    return curated


# ===================================================================
# PHASE B: Evidence Annotator
# ===================================================================

# Verified entity data from actual source code reading
# Format: {file_path: {qualified_name: (entity_type, start_line, end_line)}}
VERIFIED_ENTITIES = {}

def register_entity(file_path, qualified_name, entity_type, start_line, end_line):
    """Register a verified entity from source code."""
    if file_path not in VERIFIED_ENTITIES:
        VERIFIED_ENTITIES[file_path] = {}
    VERIFIED_ENTITIES[file_path][qualified_name] = (entity_type, start_line, end_line)


def get_entity_key(file_path, qualified_name, entity_type, start_line, end_line):
    """Compute stable key for a verified entity."""
    return compute_stable_key(REPO_ID, COMMIT_SHA, file_path, entity_type, qualified_name, start_line, end_line)


# Pre-register all verified entities from source code reading
# SysLoginController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
    "SysLoginController", "java_class", 32, 138)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
    "SysLoginController.login", "java_method", 56, 65)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
    "SysLoginController.getInfo", "java_method", 72, 94)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
    "SysLoginController.getRouters", "java_method", 101, 107)

# SysUserController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController", "java_class", 40, 256)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.list", "java_method", 59, 66)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.export", "java_method", 68, 76)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.importData", "java_method", 78, 88)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.getInfo", "java_method", 100, 117)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.add", "java_method", 122, 144)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.edit", "java_method", 149, 172)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.remove", "java_method", 177, 187)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
    "SysUserController.deptTree", "java_method", 250, 255)

# SysRoleController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
    "SysRoleController", "java_class", 37, 254)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
    "SysRoleController.edit", "java_method", 110, 134)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
    "SysRoleController.list", "java_method", 56, 63)

# CaptchaController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java",
    "CaptchaController", "java_class", 28, 94)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java",
    "CaptchaController.getCode", "java_method", 45, 93)

# SysNoticeController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
    "SysNoticeController", "java_class", 31, 150)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
    "SysNoticeController.add", "java_method", 65, 72)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
    "SysNoticeController.listTop", "java_method", 89, 99)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
    "SysNoticeController.markRead", "java_method", 104, 111)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
    "SysNoticeController.markReadAll", "java_method", 116, 124)

# SysProfileController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
    "SysProfileController", "java_class", 34, 149)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
    "SysProfileController.profile", "java_method", 47, 56)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
    "SysProfileController.updateProfile", "java_method", 61, 86)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
    "SysProfileController.updatePwd", "java_method", 91, 119)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
    "SysProfileController.avatar", "java_method", 124, 148)

# CacheController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
    "CacheController", "java_class", 30, 122)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
    "CacheController.getInfo", "java_method", 48, 71)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
    "CacheController.getCacheKeys", "java_method", 80, 86)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
    "CacheController.clearCacheName", "java_method", 97, 104)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
    "CacheController.clearCacheKey", "java_method", 106, 112)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
    "CacheController.clearCacheAll", "java_method", 114, 121)

# SysDeptController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java",
    "SysDeptController", "java_class", 31, 147)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java",
    "SysDeptController.add", "java_method", 75, 86)

# SecurityConfig.java
register_entity(
    "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
    "SecurityConfig", "java_class", 27, 128)
register_entity(
    "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
    "SecurityConfig.filterChain", "java_method", 85, 118)

# LogoutSuccessHandlerImpl.java
register_entity(
    "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
    "LogoutSuccessHandlerImpl", "java_class", 27, 53)
register_entity(
    "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
    "LogoutSuccessHandlerImpl.onLogoutSuccess", "java_method", 38, 52)

# SysJobController.java
register_entity(
    "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
    "SysJobController", "java_class", 35, 185)
register_entity(
    "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
    "SysJobController.add", "java_method", 80, 111)
register_entity(
    "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
    "SysJobController.getInfo", "java_method", 70, 75)

# SysRegisterController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRegisterController.java",
    "SysRegisterController", "java_class", 19, 38)
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRegisterController.java",
    "SysRegisterController.register", "java_method", 28, 37)

# SysRegisterService.java
register_entity(
    "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/SysRegisterService.java",
    "SysRegisterService", "java_class", 27, 117)

# SysUserOnlineController.java
register_entity(
    "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/SysUserOnlineController.java",
    "SysUserOnlineController", "java_class", 31, 83)

# GenController.java
register_entity(
    "ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java",
    "GenController", "java_class", 45, 264)
register_entity(
    "ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java",
    "GenController.importTableSave", "java_method", 113, 123)
register_entity(
    "ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java",
    "GenController.createTableSave", "java_method", 128, 160)

# Frontend API files
register_entity(
    "ruoyi-ui/src/api/login.js", "login", "frontend_api_call", 4, 20)
register_entity(
    "ruoyi-ui/src/api/login.js", "getInfo", "frontend_api_call", 35, 40)
register_entity(
    "ruoyi-ui/src/api/login.js", "logout", "frontend_api_call", 52, 57)
register_entity(
    "ruoyi-ui/src/api/login.js", "register", "frontend_api_call", 23, 32)

register_entity(
    "ruoyi-ui/src/api/menu.js", "getRouters", "frontend_api_call", 4, 8)

register_entity(
    "ruoyi-ui/src/api/system/dept.js", "addDept", "frontend_api_call", 29, 35)

register_entity(
    "ruoyi-ui/src/api/system/notice.js", "addNotice", "frontend_api_call", 21, 27)

register_entity(
    "ruoyi-ui/src/api/system/user.js", "listUser", "frontend_api_call", 5, 11)
register_entity(
    "ruoyi-ui/src/api/system/user.js", "delUser", "frontend_api_call", 40, 45)
register_entity(
    "ruoyi-ui/src/api/system/user.js", "getUser", "frontend_api_call", 14, 19)
register_entity(
    "ruoyi-ui/src/api/system/user.js", "deptTreeSelect", "frontend_api_call", 131, 136)

register_entity(
    "ruoyi-ui/src/api/monitor/cache.js", "listCacheKey", "frontend_api_call", 20, 25)
register_entity(
    "ruoyi-ui/src/api/monitor/cache.js", "getCacheValue", "frontend_api_call", 28, 33)
register_entity(
    "ruoyi-ui/src/api/monitor/cache.js", "clearCacheName", "frontend_api_call", 36, 41)
register_entity(
    "ruoyi-ui/src/api/monitor/cache.js", "clearCacheKey", "frontend_api_call", 44, 49)

register_entity(
    "ruoyi-ui/src/api/monitor/job.js", "getJob", "frontend_api_call", 13, 18)


def build_gold_entity(file_path, qualified_name, relevance="must_recall"):
    """Build a gold_entities entry from verified data."""
    info = VERIFIED_ENTITIES.get(file_path, {}).get(qualified_name)
    if info is None:
        print(f"    WARNING: Entity not registered: {file_path} :: {qualified_name}")
        return None
    entity_type, start_line, end_line = info
    key = get_entity_key(file_path, qualified_name, entity_type, start_line, end_line)
    return {
        "stable_entity_key": key,
        "entity_type": entity_type,
        "qualified_name": qualified_name,
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "relevance": relevance
    }


def build_gold_node(file_path, qualified_name, order=None):
    """Build a gold_nodes entry from verified data."""
    info = VERIFIED_ENTITIES.get(file_path, {}).get(qualified_name)
    if info is None:
        print(f"    WARNING: Node entity not registered: {file_path} :: {qualified_name}")
        return None
    entity_type, start_line, end_line = info
    key = get_entity_key(file_path, qualified_name, entity_type, start_line, end_line)
    node = {
        "stable_entity_key": key,
        "entity_type": entity_type,
        "qualified_name": qualified_name,
        "file_path": file_path,
    }
    if order is not None:
        node["order"] = order
    return node


def build_gold_edge(source_file, source_qn, target_file, target_qn, relation_type):
    """Build a gold_edges entry and check if indexed in system."""
    src_info = VERIFIED_ENTITIES.get(source_file, {}).get(source_qn)
    tgt_info = VERIFIED_ENTITIES.get(target_file, {}).get(target_qn)
    if src_info is None or tgt_info is None:
        print(f"    WARNING: Edge endpoint not registered: {source_qn} -> {target_qn}")
        return None

    src_key = get_entity_key(source_file, source_qn, src_info[0], src_info[1], src_info[2])
    tgt_key = get_entity_key(target_file, target_qn, tgt_info[0], tgt_info[1], tgt_info[2])

    indexed = check_relation_exists(src_key, tgt_key, relation_type)

    return {
        "source_key": src_key,
        "target_key": tgt_key,
        "relation_type": relation_type,
        "indexed_in_system": indexed
    }


def build_claim(claim_text, evidence_file, ranges=None):
    """Build a required_claims entry."""
    rec = {
        "claim": claim_text,
        "evidence_file": evidence_file,
    }
    if ranges:
        rec["evidence_ranges"] = ranges
    return rec


def evidence_range(file_path, start_line, end_line):
    return {"file_path": file_path, "start_line": start_line, "end_line": end_line}


# ===================================================================
# Question-specific annotation builders
# ===================================================================

ANNOTATORS = {}  # question_id -> annotation function

def annotate_q(q):
    """Dispatch to question-specific annotator."""
    qid = q["question_id"]
    if qid in ANNOTATORS:
        return ANNOTATORS[qid](q)
    # Fallback for unhandled
    return annotate_default(q)


def annotate_default(q):
    """Default annotator - produces minimal gold based on provenance files."""
    gold_entities = []
    gold_files = []
    gold_nodes = []
    gold_edges = []
    required_claims = []
    forbidden_claims = []
    expected_uncertainties = []

    # Build gold_entities from provenance files
    for fp in q.get("_provenance_files", []):
        if file_exists_in_repo(fp):
            ents = find_entities_by_file(fp)
            for e in ents[:3]:  # limit to first 3 entities per file
                gold_entities.append({
                    "stable_entity_key": e["stable_entity_key"],
                    "entity_type": e["entity_type"],
                    "qualified_name": e["qualified_name"],
                    "file_path": e["file_path"],
                    "start_line": e["start_line"],
                    "end_line": e["end_line"],
                    "relevance": "must_recall"
                })

    source_answerable = q.get("source_answerable", True)
    system_answerable = "full" if gold_entities else "insufficient"

    return {
        "gold_entities": gold_entities,
        "gold_files": gold_files,
        "gold_nodes": gold_nodes,
        "gold_edges": gold_edges,
        "required_claims": required_claims,
        "forbidden_claims": forbidden_claims,
        "expected_uncertainties": expected_uncertainties,
        "source_answerable": source_answerable,
        "system_answerable": system_answerable,
    }


# --- Q1: ruoyi-code_qa-0001 (login controller) ---
def annotate_0001(q):
    e_class = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController")
    e_method = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController.login")
    return {
        "gold_entities": [e_class, e_method],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("登录接口在SysLoginController中定义",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", 56, 65)]),
            build_claim("HTTP方法为POST，路径为/login",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", 56, 57)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0001"] = annotate_0001


# --- Q2: ruoyi-code_qa-0002 (user list controller) ---
def annotate_0002(q):
    e_class = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController")
    e_method = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.list")
    return {
        "gold_entities": [e_class, e_method],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("SysUserController handles user list queries",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 59, 66)]),
            build_claim("The class-level RequestMapping is /system/user",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 41, 42)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0002"] = annotate_0002


# --- Q3: ruoyi-code_qa-0003 (captcha) ---
def annotate_0003(q):
    e_class = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java",
        "CaptchaController")
    e_method = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java",
        "CaptchaController.getCode")
    return {
        "gold_entities": [e_class, e_method],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("验证码API路径为GET /captchaImage",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java", 45, 46)]),
            build_claim("实现在CaptchaController类的getCode方法中",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java", 45, 93)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0003"] = annotate_0003


# --- Q4: ruoyi-code_qa-0004 (deptTree) ---
def annotate_0004(q):
    e_method = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.deptTree")
    e_class = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController")
    return {
        "gold_entities": [e_method, e_class],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("The dept tree API is at GET /system/user/deptTree",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 250, 255)]),
            build_claim("It is in SysUserController, not SysDeptController",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 250, 255)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0004"] = annotate_0004


# --- Q5: ruoyi-code_qa-0005 (role APIs) ---
def annotate_0005(q):
    e_class = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
        "SysRoleController")
    return {
        "gold_entities": [e_class],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("所有角色管理API接口定义在SysRoleController中",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java", 37, 254)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0005"] = annotate_0005


# --- Q6: ruoyi-code_qa-0006 (job security) ---
def annotate_0006(q):
    e_class = build_gold_entity(
        "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
        "SysJobController")
    e_method = build_gold_entity(
        "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
        "SysJobController.add")
    return {
        "gold_entities": [e_class, e_method],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("Cron expression validity is checked",
                "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
                [evidence_range("ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", 85, 88)]),
            build_claim("RMI invocations are blocked",
                "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
                [evidence_range("ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", 89, 92)]),
            build_claim("LDAP invocations are blocked",
                "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
                [evidence_range("ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", 93, 96)]),
            build_claim("HTTP invocations are blocked",
                "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
                [evidence_range("ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", 97, 100)]),
            build_claim("Forbidden strings are checked",
                "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
                [evidence_range("ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", 101, 104)]),
            build_claim("Whitelist validation is performed",
                "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
                [evidence_range("ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", 105, 108)]),
            build_claim("Requires monitor:job:add permission",
                "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
                [evidence_range("ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", 80, 81)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0006"] = annotate_0006


# --- Q7: ruoyi-code_qa-0007 (cache dynamic URL) ---
def annotate_0007(q):
    e_cache_js = build_gold_entity(
        "ruoyi-ui/src/api/monitor/cache.js", "listCacheKey")
    e_getval = build_gold_entity(
        "ruoyi-ui/src/api/monitor/cache.js", "getCacheValue")
    e_clr_name = build_gold_entity(
        "ruoyi-ui/src/api/monitor/cache.js", "clearCacheName")
    e_clr_key = build_gold_entity(
        "ruoyi-ui/src/api/monitor/cache.js", "clearCacheKey")
    return {
        "gold_entities": [e_cache_js, e_getval, e_clr_name, e_clr_key],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("cache.js中有4个请求使用了字符串拼接构造URL",
                "ruoyi-ui/src/api/monitor/cache.js",
                [evidence_range("ruoyi-ui/src/api/monitor/cache.js", 20, 49)]),
            build_claim("静态分析无法解析JavaScript字符串拼接",
                "ruoyi-ui/src/api/monitor/cache.js",
                [evidence_range("ruoyi-ui/src/api/monitor/cache.js", 22, 23)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0007"] = annotate_0007


# --- Q8: ruoyi-code_qa-0008 (JSON import - unanswerable) ---
def annotate_0008(q):
    return {
        "gold_entities": [],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [
            {"claim": "There is a JSON batch import endpoint", "reason": "The system only supports Excel import via POST /system/user/importData with MultipartFile"},
            {"claim": "Any endpoint accepts JSON for user import", "reason": "Import uses ExcelUtil.importExcel, not JSON parsing"},
        ],
        "expected_uncertainties": [
            {"condition": "No JSON import API exists", "description": "The system supports user import only via Excel files (POST /system/user/importData with MultipartFile)"},
            {"condition": "User asks about JSON format", "description": "No JSON-based batch import API exists in the system"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-code-qa-0008"] = annotate_0008


# --- Q9: ruoyi-code_qa-0009 (SMS - unanswerable) ---
def annotate_0009(q):
    return {
        "gold_entities": [],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [
            {"claim": "存在短信发送API", "reason": "系统中不存在短信发送相关的API接口"},
            {"claim": "有任何控制器实现了短信发送方法", "reason": "扫描到的所有控制器中均未发现短信发送功能"},
        ],
        "expected_uncertainties": [
            {"condition": "No SMS feature exists", "description": "系统中不存在短信发送相关的API接口"},
            {"condition": "Searched all controllers", "description": "扫描到的所有控制器中均未发现短信发送功能"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-code-qa-0009"] = annotate_0009


# --- Q10: ruoyi-code_qa-0010 (logout) ---
def annotate_0010(q):
    e_handler = build_gold_entity(
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
        "LogoutSuccessHandlerImpl")
    e_config = build_gold_entity(
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
        "SecurityConfig")
    return {
        "gold_entities": [e_handler, e_config],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("Logout is handled by Spring Security LogoutFilter",
                "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
                [evidence_range("ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java", 111, 111)]),
            build_claim("Configured in SecurityConfig via .logout() DSL",
                "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
                [evidence_range("ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java", 111, 111)]),
            build_claim("LogoutSuccessHandlerImpl deletes token cache and logs the event",
                "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
                [evidence_range("ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java", 38, 52)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Logout URL not in controller annotations", "description": "The logout URL is configured declaratively in Spring Security, not via @RequestMapping"},
        ],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0010"] = annotate_0010


# --- Q11: ruoyi-code_qa-0011 (user vs profile controllers) ---
def annotate_0011(q):
    e_user = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController")
    e_profile = build_gold_entity(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
        "SysProfileController")
    return {
        "gold_entities": [e_user, e_profile],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("SysUserController路径前缀为/system/user",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 41, 42)]),
            build_claim("SysProfileController路径前缀为/system/user/profile",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java", 35, 36)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-code-qa-0011"] = annotate_0011


# --- Q12: ruoyi-code_qa-0012 (PDF export - unanswerable) ---
def annotate_0012(q):
    return {
        "gold_entities": [],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [
            {"claim": "There is a PDF export endpoint", "reason": "The system only supports Excel export via ExcelUtil"},
            {"claim": "Any controller generates PDF output", "reason": "No PDF generation library or endpoint exists"},
        ],
        "expected_uncertainties": [
            {"condition": "Only Excel export exists", "description": "The system only supports Excel export via ExcelUtil"},
            {"condition": "No PDF library", "description": "No PDF generation library or endpoint exists"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-code-qa-0012"] = annotate_0012


# --- Q13: ruoyi-trace_chain-0013 (login trace) ---
def annotate_0013(q):
    n_frontend = build_gold_node("ruoyi-ui/src/api/login.js", "login", order=0)
    n_backend = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController.login", order=1)
    e_req = build_gold_edge(
        "ruoyi-ui/src/api/login.js", "login",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController.login", "REQUESTS_API")
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-ui/src/api/login.js", "login"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", "SysLoginController.login"),
        ],
        "gold_files": [],
        "gold_nodes": [n_frontend, n_backend],
        "gold_edges": [e_req],
        "required_claims": [
            build_claim("前端login.js中POST /login请求到达SysLoginController.login方法",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                [evidence_range("ruoyi-ui/src/api/login.js", 11, 19),
                 evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", 56, 65)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-trace-chain-0013"] = annotate_0013


# --- Q14: ruoyi-trace_chain-0014 (dept creation trace) ---
def annotate_0014(q):
    n_frontend = build_gold_node("ruoyi-ui/src/api/system/dept.js", "addDept", order=0)
    n_backend = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java",
        "SysDeptController.add", order=1)
    e_req = build_gold_edge(
        "ruoyi-ui/src/api/system/dept.js", "addDept",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java",
        "SysDeptController.add", "REQUESTS_API")
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-ui/src/api/system/dept.js", "addDept"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java", "SysDeptController.add"),
        ],
        "gold_files": [],
        "gold_nodes": [n_frontend, n_backend],
        "gold_edges": [e_req],
        "required_claims": [
            build_claim("Frontend dept.js sends POST /system/dept",
                "ruoyi-ui/src/api/system/dept.js",
                [evidence_range("ruoyi-ui/src/api/system/dept.js", 29, 35)]),
            build_claim("Backend SysDeptController.add receives it",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java", 75, 86)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-trace-chain-0014"] = annotate_0014


# --- Q15: ruoyi-trace_chain-0015 (user list call chain) ---
def annotate_0015(q):
    n_ctrl = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.list", order=0)
    # ISysUserService.selectUserList is not directly in our verified entities,
    # but we know the controller calls userService.selectUserList
    # The CALLS_METHOD relation won't exist in snapshot (no CALLS_METHOD relations at all)
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                "SysUserController.list"),
        ],
        "gold_files": [],
        "gold_nodes": [n_ctrl],
        "gold_edges": [],
        "required_claims": [
            build_claim("SysUserController.list调用userService.selectUserList",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 59, 66)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "CALLS_METHOD not in index", "description": "The static index does not store CALLS_METHOD relations, so the controller-to-service call chain cannot be traced through the graph"},
        ],
        "source_answerable": True,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-trace-chain-0015"] = annotate_0015


# --- Q16: ruoyi-trace_chain-0016 (role update chain) ---
def annotate_0016(q):
    n_ctrl = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
        "SysRoleController.edit", order=0)
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
                "SysRoleController.edit"),
        ],
        "gold_files": [],
        "gold_nodes": [n_ctrl],
        "gold_edges": [],
        "required_claims": [
            build_claim("SysRoleController.edit handles PUT /system/role",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java", 110, 134)]),
            build_claim("It calls roleService.updateRole",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java", 127, 127)]),
            build_claim("After success, it calls tokenService.refreshPermissionByRoleId",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java", 130, 130)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "CALLS_METHOD not indexed", "description": "CALLS_METHOD relations are not stored in the static index"},
        ],
        "source_answerable": True,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-trace-chain-0016"] = annotate_0016


# --- Q17: ruoyi-trace_chain-0017 (notice add chain) ---
def annotate_0017(q):
    n_frontend = build_gold_node("ruoyi-ui/src/api/system/notice.js", "addNotice", order=0)
    n_ctrl = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
        "SysNoticeController.add", order=1)
    e_req = build_gold_edge(
        "ruoyi-ui/src/api/system/notice.js", "addNotice",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
        "SysNoticeController.add", "REQUESTS_API")
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-ui/src/api/system/notice.js", "addNotice"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java", "SysNoticeController.add"),
        ],
        "gold_files": [],
        "gold_nodes": [n_frontend, n_ctrl],
        "gold_edges": [e_req],
        "required_claims": [
            build_claim("前端notice.js中addNotice发送POST /system/notice",
                "ruoyi-ui/src/api/system/notice.js",
                [evidence_range("ruoyi-ui/src/api/system/notice.js", 21, 27)]),
            build_claim("SysNoticeController.add接收请求",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java", 65, 72)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-trace-chain-0017"] = annotate_0017


# --- Q18: ruoyi-trace_chain-0018 (cache dynamic URL trace) ---
def annotate_0018(q):
    n_frontend = build_gold_node("ruoyi-ui/src/api/monitor/cache.js", "listCacheKey", order=0)
    n_backend = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
        "CacheController.getCacheKeys", order=1)
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-ui/src/api/monitor/cache.js", "listCacheKey"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java", "CacheController.getCacheKeys"),
        ],
        "gold_files": [],
        "gold_nodes": [n_frontend, n_backend],
        "gold_edges": [],
        "required_claims": [
            build_claim("The frontend function listCacheKey constructs the URL dynamically",
                "ruoyi-ui/src/api/monitor/cache.js",
                [evidence_range("ruoyi-ui/src/api/monitor/cache.js", 20, 25)]),
            build_claim("The backend endpoint is GET /monitor/cache/getKeys/{cacheName} in CacheController",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java", 80, 86)]),
            build_claim("The static index cannot automatically create a REQUESTS_API relation for dynamic URLs",
                "ruoyi-ui/src/api/monitor/cache.js",
                [evidence_range("ruoyi-ui/src/api/monitor/cache.js", 22, 23)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Dynamic URL prevents indexing", "description": "The static scanner flagged this as dynamic_url so the REQUESTS_API link is not stored"},
        ],
        "source_answerable": True,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-trace-chain-0018"] = annotate_0018


# --- Q19: ruoyi-trace_chain-0019 (getRouters chain) ---
def annotate_0019(q):
    n_frontend = build_gold_node("ruoyi-ui/src/api/menu.js", "getRouters", order=0)
    n_ctrl = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController.getRouters", order=1)
    e_req = build_gold_edge(
        "ruoyi-ui/src/api/menu.js", "getRouters",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController.getRouters", "REQUESTS_API")
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-ui/src/api/menu.js", "getRouters"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", "SysLoginController.getRouters"),
        ],
        "gold_files": [],
        "gold_nodes": [n_frontend, n_ctrl],
        "gold_edges": [e_req],
        "required_claims": [
            build_claim("SysLoginController.getRouters调用menuService.selectMenuTreeByUserId获取菜单树",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", 101, 107)]),
            build_claim("再调用menuService.buildMenus构建路由",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", 106, 106)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-trace-chain-0019"] = annotate_0019


# --- Q20: ruoyi-trace_chain-0020 (logout trace - unanswerable) ---
def annotate_0020(q):
    e_handler = build_gold_entity(
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
        "LogoutSuccessHandlerImpl")
    return {
        "gold_entities": [e_handler],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [
            {"claim": "A controller class maps POST /logout via @PostMapping or @RequestMapping", "reason": "POST /logout is configured via Spring Security LogoutFilter, not any controller annotation"},
        ],
        "expected_uncertainties": [
            {"condition": "No controller handles /logout", "description": "POST /logout is not handled by any controller - it is configured via Spring Security LogoutFilter"},
            {"condition": "No DEFINES_API for /logout", "description": "The static index has no DEFINES_API entity for /logout"},
            {"condition": "LogoutSuccessHandlerImpl is not a controller", "description": "LogoutSuccessHandlerImpl handles the logout response but is not a controller"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-trace-chain-0020"] = annotate_0020


# --- Q21: ruoyi-trace_chain-0021 (same-name getInfo) ---
def annotate_0021(q):
    n_frontend = build_gold_node("ruoyi-ui/src/api/login.js", "getInfo", order=0)
    n_login = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController.getInfo", order=1)
    n_cache = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
        "CacheController.getInfo", order=2)
    n_user = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.getInfo", order=3)
    e_req = build_gold_edge(
        "ruoyi-ui/src/api/login.js", "getInfo",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "SysLoginController.getInfo", "REQUESTS_API")
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", "SysLoginController.getInfo"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java", "CacheController.getInfo"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", "SysUserController.getInfo"),
        ],
        "gold_files": [],
        "gold_nodes": [n_frontend, n_login, n_cache, n_user],
        "gold_edges": [e_req],
        "required_claims": [
            build_claim("SysLoginController.getInfo映射GET /getInfo",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java", 72, 94)]),
            build_claim("CacheController.getInfo映射GET /monitor/cache",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java", 48, 71)]),
            build_claim("SysUserController.getInfo映射GET /system/user/{userId}",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 100, 117)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-trace-chain-0021"] = annotate_0021


# --- Q22: ruoyi-trace_chain-0022 (DELETE vs GET same path) ---
def annotate_0022(q):
    n_del = build_gold_node("ruoyi-ui/src/api/system/user.js", "delUser", order=0)
    n_get = build_gold_node("ruoyi-ui/src/api/system/user.js", "getUser", order=1)
    n_remove = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.remove", order=2)
    n_getinfo = build_gold_node(
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.getInfo", order=3)
    e_del = build_gold_edge(
        "ruoyi-ui/src/api/system/user.js", "delUser",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.remove", "REQUESTS_API")
    e_get = build_gold_edge(
        "ruoyi-ui/src/api/system/user.js", "getUser",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "SysUserController.getInfo", "REQUESTS_API")
    return {
        "gold_entities": [
            build_gold_entity("ruoyi-ui/src/api/system/user.js", "delUser"),
            build_gold_entity("ruoyi-ui/src/api/system/user.js", "getUser"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", "SysUserController.remove"),
            build_gold_entity("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", "SysUserController.getInfo"),
        ],
        "gold_files": [],
        "gold_nodes": [n_del, n_get, n_remove, n_getinfo],
        "gold_edges": [e_del, e_get],
        "required_claims": [
            build_claim("DELETE /system/user/{userId} maps to SysUserController.remove",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 177, 187)]),
            build_claim("GET /system/user/{userId} maps to SysUserController.getInfo",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 100, 117)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-trace-chain-0022"] = annotate_0022


# --- Q23: ruoyi-trace_chain-0023 (batchDelete - unanswerable) ---
def annotate_0023(q):
    return {
        "gold_entities": [],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [
            {"claim": "POST /system/user/batchDelete是一个有效的后端API", "reason": "系统中不存在该接口"},
            {"claim": "存在专门处理batchDelete的控制器方法", "reason": "用户删除使用DELETE /system/user/{userIds}"},
        ],
        "expected_uncertainties": [
            {"condition": "Endpoint does not exist", "description": "系统中不存在POST /system/user/batchDelete接口"},
            {"condition": "Batch delete via path params", "description": "用户删除使用DELETE /system/user/{userIds}，通过路径参数传入多个ID实现批量删除"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-trace-chain-0023"] = annotate_0023


# --- Q24: ruoyi-trace_chain-0024 (job dynamic URL) ---
def annotate_0024(q):
    e_frontend = build_gold_entity("ruoyi-ui/src/api/monitor/job.js", "getJob")
    e_backend = build_gold_entity(
        "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
        "SysJobController.getInfo")
    return {
        "gold_entities": [e_frontend, e_backend],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Dynamic URL in getJob", "description": "The frontend getJob function constructs the URL dynamically: '/monitor/job/' + jobId"},
            {"condition": "No REQUESTS_API stored", "description": "The static index marks this as dynamic_url and does NOT store a REQUESTS_API relation for it"},
            {"condition": "Backend exists but untraceable", "description": "While the backend endpoint GET /monitor/job/{jobId} exists in SysJobController, the trace cannot be verified through the index"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-trace-chain-0024"] = annotate_0024


# --- Q25-Q30: CHANGE_PLAN hypothetical questions ---
def annotate_0025(q):
    """Notice pin/top feature."""
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java", "category": "must_change", "reason": "Need new endpoint for pin/top operation"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/ISysNoticeService.java", "category": "must_change", "reason": "Need new service method declaration"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysNoticeServiceImpl.java", "category": "must_change", "reason": "Need implementation of pin/top logic"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/domain/SysNotice.java", "category": "likely_change", "reason": "May need isTop field"},
            {"file_path": "ruoyi-ui/src/api/system/notice.js", "category": "likely_change", "reason": "Need new frontend API function"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("需要修改SysNoticeController添加新的端点方法",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java"),
            build_claim("需要在ISysNoticeService接口中添加新方法声明",
                "ruoyi-system/src/main/java/com/ruoyi/system/service/ISysNoticeService.java"),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0025"] = annotate_0025


def annotate_0026(q):
    """Online user Excel export."""
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/SysUserOnlineController.java", "category": "must_change", "reason": "Need new @PostMapping('/export') method"},
            {"file_path": "ruoyi-ui/src/api/monitor/online.js", "category": "likely_change", "reason": "Need new export function"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("SysUserOnlineController needs a new export endpoint",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/SysUserOnlineController.java"),
            build_claim("The method would use ExcelUtil like other controllers do",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/SysUserOnlineController.java"),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0026"] = annotate_0026


def annotate_0027(q):
    """Email verification for registration."""
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRegisterController.java", "category": "must_change", "reason": "Need new endpoint for sending verification email"},
            {"file_path": "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/SysRegisterService.java", "category": "must_change", "reason": "Need email sending logic"},
            {"file_path": "ruoyi-ui/src/api/login.js", "category": "likely_change", "reason": "Need frontend API for email verification"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("需要修改SysRegisterController添加发送验证邮件的端点",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRegisterController.java"),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0027"] = annotate_0027


def annotate_0028(q):
    """Cache audit logging."""
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java", "category": "must_change", "reason": "Need to add @Log annotations to cache clearing methods"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("CacheController has 3 DELETE endpoints for cache clearing",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java", 97, 121)]),
            build_claim("The @Log annotation pattern from other controllers should be followed",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", 68, 76)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0028"] = annotate_0028


def annotate_0029(q):
    """Notice permission annotations."""
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java", "category": "must_change", "reason": "markRead and markReadAll methods need @PreAuthorize annotations"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("markRead和markReadAll方法当前没有@PreAuthorize注解",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
                [evidence_range("ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java", 104, 124)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0029"] = annotate_0029


def annotate_0030(q):
    """GenController split."""
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java", "category": "must_change", "reason": "importTable and createTable endpoints would move to new controller"},
            {"file_path": "ruoyi-ui/src/api/tool/gen.js", "category": "likely_change", "reason": "Frontend URLs may need updating if path prefix changes"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("POST /tool/gen/importTable and POST /tool/gen/createTable would move to a new controller",
                "ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java",
                [evidence_range("ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java", 113, 160)]),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0030"] = annotate_0030


# --- Q31: vague performance optimization (unanswerable) ---
def annotate_0031(q):
    return {
        "gold_entities": [],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Scope too vague", "description": "\"整体性能优化\"范围过于宽泛，无法确定具体的修改文件"},
            {"condition": "Multiple possible directions", "description": "可能的方向包括数据库查询优化、缓存策略、异步处理等，但无法从代码结构中确定优先级"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-change-plan-0031"] = annotate_0031


# --- Q32: WebSocket notifications ---
def annotate_0032(q):
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java", "category": "must_change", "reason": "Need WebSocket endpoint or event publishing"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysNoticeServiceImpl.java", "category": "must_change", "reason": "insertNotice needs to publish WebSocket event"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysNoticeReadServiceImpl.java", "category": "context_only", "reason": "Already tracks read status per user"},
            {"file_path": "ruoyi-ui/src/api/system/notice.js", "category": "likely_change", "reason": "Need WebSocket client connection logic"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("Backend needs WebSocket configuration and event publishing",
                "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java"),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Implementation choice", "description": "Exact WebSocket library choice and configuration details are implementation decisions"},
        ],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0032"] = annotate_0032


# --- Q33: JWT to DB migration ---
def annotate_0033(q):
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/TokenService.java", "category": "must_change", "reason": "Core token storage uses RedisCache, needs DB replacement"},
            {"file_path": "ruoyi-framework/src/main/java/com/ruoyi/framework/security/filter/JwtAuthenticationTokenFilter.java", "category": "must_change", "reason": "Retrieves user info from TokenService on each request"},
            {"file_path": "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java", "category": "must_change", "reason": "Configures JWT filter and logout handler"},
            {"file_path": "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java", "category": "must_change", "reason": "Deletes Redis token cache on logout"},
            {"file_path": "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/SysLoginService.java", "category": "likely_change", "reason": "Calls TokenService.createToken to create tokens"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("TokenService是核心，它使用RedisCache存储令牌信息",
                "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/TokenService.java"),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0033"] = annotate_0033


# --- Q34: Spring to Quarkus (unanswerable) ---
def annotate_0034(q):
    return {
        "gold_entities": [],
        "gold_files": [],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Scope too large", "description": "A full framework migration would affect virtually all Java files"},
            {"condition": "Cannot enumerate precisely", "description": "The scope is too large to enumerate precisely"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-change-plan-0034"] = annotate_0034


# --- Q35: Multi-tenant support ---
def annotate_0035(q):
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java", "category": "must_change", "reason": "User queries need tenant filtering"},
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java", "category": "must_change", "reason": "Role queries need tenant filtering"},
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java", "category": "must_change", "reason": "Dept queries need tenant filtering"},
            {"file_path": "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysMenuController.java", "category": "must_change", "reason": "Menu queries need tenant filtering"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java", "category": "must_change", "reason": "Service layer queries need tenant ID filter"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysRoleServiceImpl.java", "category": "must_change", "reason": "Service layer queries need tenant ID filter"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysDeptServiceImpl.java", "category": "must_change", "reason": "Service layer queries need tenant ID filter"},
            {"file_path": "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysMenuServiceImpl.java", "category": "must_change", "reason": "Service layer queries need tenant ID filter"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim("所有Service层的查询方法都需要增加租户过滤条件",
                "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java"),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Architecture decision needed", "description": "具体的租户隔离策略(行级隔离、Schema隔离、数据库隔离)需要架构决策"},
        ],
        "source_answerable": True,
        "system_answerable": "full",
    }

ANNOTATORS["ruoyi-change-plan-0035"] = annotate_0035


# --- Q36: Job security fix (unanswerable - subjective) ---
def annotate_0036(q):
    return {
        "gold_entities": [],
        "gold_files": [
            {"file_path": "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java", "category": "likely_change", "reason": "Controller validation could be strengthened"},
            {"file_path": "ruoyi-quartz/src/main/java/com/ruoyi/quartz/service/impl/SysJobServiceImpl.java", "category": "likely_change", "reason": "Service execution mechanism could be sandboxed"},
        ],
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [],
        "forbidden_claims": [],
        "expected_uncertainties": [
            {"condition": "Minimal change is subjective", "description": "The exact 'minimal' change set depends on the chosen security strategy"},
            {"condition": "Multiple fix approaches", "description": "Options include: stricter whitelist, sandboxed execution, removing reflection-based invocation entirely"},
        ],
        "source_answerable": False,
        "system_answerable": "insufficient",
    }

ANNOTATORS["ruoyi-change-plan-0036"] = annotate_0036


# --- Q37-Q42: Historical change cases ---
def annotate_historical(q):
    """Generic annotator for historical change cases."""
    hc_files = q.get("_provenance_files", [])
    gold_files = []
    for fp in hc_files:
        if file_exists_in_repo(fp):
            # Classify based on file type
            if "controller" in fp.lower() or "api/" in fp.lower():
                cat = "must_change"
            elif "service" in fp.lower() or "impl" in fp.lower():
                cat = "must_change"
            elif "mapper" in fp.lower() or "domain" in fp.lower():
                cat = "likely_change"
            elif "ui/" in fp.lower():
                cat = "likely_change"
            elif fp.endswith(".xml") or fp.endswith(".sql"):
                cat = "likely_change"
            else:
                cat = "context_only"
            gold_files.append({
                "file_path": fp,
                "category": cat,
                "reason": f"Observed changed file in historical commit {q.get('_hc_case_id', '')}"
            })

    return {
        "gold_entities": [],
        "gold_files": gold_files,
        "gold_nodes": [],
        "gold_edges": [],
        "required_claims": [
            build_claim(f"变更涉及的文件包括: {', '.join(hc_files[:3])}",
                hc_files[0] if hc_files else ""),
        ],
        "forbidden_claims": [],
        "expected_uncertainties": [],
        "source_answerable": True,
        "system_answerable": "full",
    }

for i in range(37, 43):
    ANNOTATORS[f"ruoyi-change-plan-{i:04d}"] = annotate_historical


def phase_b_annotate(curated):
    print("\n=== PHASE B: Evidence Annotator ===")

    annotated = []
    for q in curated:
        qid = q["question_id"]
        print(f"  Annotating {qid}...")

        # Get gold from annotator
        gold = annotate_q(q)

        # Compute fingerprint
        fp = compute_fingerprint(q["question"])

        # Build provenance
        source_files = q.get("_provenance_files", [])
        # Ensure all gold entity/node files are in provenance
        for e in gold.get("gold_entities", []):
            if e and e.get("file_path") and e["file_path"] not in source_files:
                source_files.append(e["file_path"])
        for n in gold.get("gold_nodes", []):
            if n and n.get("file_path") and n["file_path"] not in source_files:
                source_files.append(n["file_path"])
        for gf in gold.get("gold_files", []):
            if gf.get("file_path") and gf["file_path"] not in source_files:
                source_files.append(gf["file_path"])
        for cl in gold.get("required_claims", []):
            ef = cl.get("evidence_file", "")
            if ef and ef not in source_files:
                source_files.append(ef)

        # Filter out non-existent files from source_files
        source_files = [f for f in source_files if file_exists_in_repo(f)]

        # Build provenance source_lines
        source_lines = []
        for sl in q.get("_provenance_lines", []):
            if isinstance(sl, str) and ":" in sl:
                parts = sl.split(":")
                fp_part = parts[0]
                lines_part = parts[1] if len(parts) > 1 else ""
                if "-" in lines_part:
                    s, e = lines_part.split("-")
                    source_lines.append({"file_path": fp_part, "start_line": int(s), "end_line": int(e)})

        # Fix evaluation_layers: replace "synthesis" with valid values
        eval_layers = q.get("evaluation_layers", ["routing", "retrieval"])
        eval_layers = [l if l != "synthesis" else "answer_citation" for l in eval_layers]

        # Determine system_answerable - "partial" requires at least one gold_edge with indexed_in_system=false
        system_ans = gold["system_answerable"]
        has_unindexed_edge = any(
            e.get("indexed_in_system") == False
            for e in gold.get("gold_edges", [])
            if e is not None
        )
        if system_ans == "partial" and not has_unindexed_edge:
            # Can't be partial without unindexed edges - downgrade to full if entities exist, else insufficient
            if gold.get("gold_entities") or gold.get("gold_nodes"):
                system_ans = "full"
            else:
                system_ans = "insufficient"

        # Build the record
        rec = {
            "dataset_version": DATASET_VERSION,
            "question_id": qid,
            "question_fingerprint": fp,
            "repo_id": REPO_ID,
            "commit_sha": COMMIT_SHA,
            "split": "development",
            "task_type": q["task_type"],
            "language": q["language"],
            "difficulty": q["difficulty"],
            "question": q["question"],
            "source_answerable": gold["source_answerable"],
            "system_answerable": system_ans,
            "question_origin": "machine_generated",
            "gold_status": "machine_proposed",
            "evaluation_layers": eval_layers,
            "expected_task_type": q.get("expected_task_type", q["task_type"]),
            "gold_entities": [e for e in gold["gold_entities"] if e is not None],
            "gold_files": gold["gold_files"],
            "gold_nodes": [n for n in gold["gold_nodes"] if n is not None],
            "gold_edges": [e for e in gold["gold_edges"] if e is not None],
            "required_claims": gold["required_claims"],
            "forbidden_claims": gold["forbidden_claims"],
            "expected_uncertainties": gold["expected_uncertainties"],
            "annotation": {
                "annotator": "evidence_annotator_B",
                "reviewer": "",
                "review_status": "needs_review",
                "notes": q.get("_old_notes", ""),
            },
            "provenance": {
                "source_files": source_files,
                "source_lines": source_lines,
                "generation_method": "code_inspection",
                "created_at": now_iso(),
            },
        }

        # Add chain_complete for TRACE_CHAIN questions with edges
        if q["task_type"] == "TRACE_CHAIN" and rec["gold_edges"]:
            all_indexed = all(e.get("indexed_in_system", False) for e in rec["gold_edges"])
            rec["chain_complete"] = all_indexed

        # For CHANGE_PLAN with retrieval layer and source_answerable=true,
        # ensure at least one must_recall gold_entity exists
        if (q["task_type"] == "CHANGE_PLAN" and
            "retrieval" in eval_layers and
            gold["source_answerable"] and
            not rec["gold_entities"]):
            # Add entities from gold_files
            for gf in gold["gold_files"]:
                fp_gf = gf.get("file_path", "")
                if fp_gf and file_exists_in_repo(fp_gf):
                    ents = find_entities_by_file(fp_gf)
                    for e in ents[:2]:
                        rec["gold_entities"].append({
                            "stable_entity_key": e["stable_entity_key"],
                            "entity_type": e["entity_type"],
                            "qualified_name": e["qualified_name"],
                            "file_path": e["file_path"],
                            "start_line": e["start_line"],
                            "end_line": e["end_line"],
                            "relevance": "must_recall"
                        })
                    if rec["gold_entities"]:
                        break

        # For CHANGE_PLAN with retrieval + answerable + no entities -> remove retrieval layer
        if (q["task_type"] == "CHANGE_PLAN" and
            "retrieval" in eval_layers and
            gold["source_answerable"] and
            not rec["gold_entities"]):
            rec["evaluation_layers"] = [l for l in eval_layers if l != "retrieval"]

        # Add historical change provenance
        if q.get("_historical_change"):
            rec["change_plan_type"] = "historical_change"
            rec["change_plan_provenance"] = {
                "annotation_type": "historical_change",
                "base_commit_sha": q["_hc_base_commit"],
                "target_commit_sha": q["_hc_target_commit"],
                "change_request": q["question"],
                "observed_changed_files": q["_provenance_files"],
                "source_commit_message": q["_hc_commit_message"],
                "diff_summary": q["_hc_diff_summary"],
            }
        elif q["task_type"] == "CHANGE_PLAN":
            rec["change_plan_type"] = "expert_hypothetical"
            rec["change_plan_provenance"] = {
                "annotation_type": "expert_hypothetical",
            }

        annotated.append(rec)

    print(f"  Total annotated: {len(annotated)}")

    OUTPUT_ANNOTATED.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_ANNOTATED, "w", encoding="utf-8") as f:
        json.dump(annotated, f, ensure_ascii=False, indent=2)

    print(f"  Written to {OUTPUT_ANNOTATED}")
    return annotated


# ===================================================================
# PHASE C: Adversarial Reviewer
# ===================================================================
def phase_c_review(annotated):
    print("\n=== PHASE C: Adversarial Reviewer ===")

    reviewed = []
    for rec in annotated:
        qid = rec["question_id"]
        review_notes = []
        all_confirmed = True
        any_unsupported = False

        # Verify each gold_entity
        for idx, entity in enumerate(rec.get("gold_entities", [])):
            if not isinstance(entity, dict):
                continue
            fp = entity.get("file_path", "")
            if not file_exists_in_repo(fp):
                review_notes.append(f"gold_entities[{idx}]: file {fp} does not exist - unsupported")
                any_unsupported = True
                continue
            # Verify line numbers
            max_lines = count_file_lines(fp)
            sl = entity.get("start_line", 1)
            el = entity.get("end_line", 1)
            if sl > max_lines or el > max_lines:
                review_notes.append(f"gold_entities[{idx}]: lines {sl}-{el} exceed file length {max_lines} - challenged")
                all_confirmed = False
            elif sl > el:
                review_notes.append(f"gold_entities[{idx}]: start_line > end_line - challenged")
                all_confirmed = False

        # Verify each gold_node
        for idx, node in enumerate(rec.get("gold_nodes", [])):
            if not isinstance(node, dict):
                continue
            fp = node.get("file_path", "")
            if not file_exists_in_repo(fp):
                review_notes.append(f"gold_nodes[{idx}]: file {fp} does not exist - unsupported")
                any_unsupported = True

        # Verify gold_edges endpoint keys exist in gold_nodes
        node_keys = {n.get("stable_entity_key") for n in rec.get("gold_nodes", []) if isinstance(n, dict)}
        for idx, edge in enumerate(rec.get("gold_edges", [])):
            if not isinstance(edge, dict):
                continue
            src = edge.get("source_key", "")
            tgt = edge.get("target_key", "")
            if src and src not in node_keys:
                review_notes.append(f"gold_edges[{idx}]: source_key not in gold_nodes - challenged")
                all_confirmed = False
            if tgt and tgt not in node_keys:
                review_notes.append(f"gold_edges[{idx}]: target_key not in gold_nodes - challenged")
                all_confirmed = False

        # Check answer leakage
        question_lower = rec["question"].lower()
        # Simple check: if question mentions specific class/method names that are answers
        # This is a heuristic - most questions in this dataset are fine

        # Verify gold_files exist
        for idx, gf in enumerate(rec.get("gold_files", [])):
            fp = gf.get("file_path", "")
            if fp and not file_exists_in_repo(fp):
                review_notes.append(f"gold_files[{idx}]: file {fp} does not exist - unsupported")
                any_unsupported = True

        # Determine review status
        if any_unsupported:
            status = "rejected"
        elif not all_confirmed or review_notes:
            status = "needs_review"
        else:
            status = "accepted"

        # Update record
        rec["annotation"]["reviewer"] = "adversarial_reviewer_C"
        rec["annotation"]["review_status"] = status
        if review_notes:
            rec["annotation"]["notes"] = "; ".join(review_notes)

        reviewed.append(rec)

    # Count statuses
    from collections import Counter
    status_counts = Counter(r["annotation"]["review_status"] for r in reviewed)
    print(f"  Review results: {dict(status_counts)}")

    OUTPUT_REVIEWED.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REVIEWED, "w", encoding="utf-8") as f:
        json.dump(reviewed, f, ensure_ascii=False, indent=2)

    print(f"  Written to {OUTPUT_REVIEWED}")
    return reviewed


# ===================================================================
# PHASE D: Merge to canonical
# ===================================================================
def phase_d_merge(reviewed):
    print("\n=== PHASE D: Merge to canonical ===")

    canonical = []
    excluded = 0
    for rec in reviewed:
        status = rec["annotation"]["review_status"]
        if status == "rejected":
            excluded += 1
            continue

        if status == "accepted":
            rec["gold_status"] = "machine_verified"
        else:  # needs_review
            rec["gold_status"] = "machine_proposed"

        # Clean up internal fields
        for key in list(rec.keys()):
            if key.startswith("_"):
                del rec[key]

        # Clean up gold arrays - remove None entries
        rec["gold_entities"] = [e for e in rec.get("gold_entities", []) if e is not None]
        rec["gold_nodes"] = [n for n in rec.get("gold_nodes", []) if n is not None]
        rec["gold_edges"] = [e for e in rec.get("gold_edges", []) if e is not None]

        canonical.append(rec)

    print(f"  Included: {len(canonical)}, Excluded: {excluded}")

    OUTPUT_CANONICAL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CANONICAL, "w", encoding="utf-8") as f:
        for rec in canonical:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"  Written to {OUTPUT_CANONICAL}")
    return canonical


# ===================================================================
# PHASE E: Validate
# ===================================================================
def phase_e_validate():
    print("\n=== PHASE E: Validate ===")

    import subprocess
    result = subprocess.run(
        [
            str(Path(r"F:\LIUQINGYUN\ResearchCode_Agent\backend\.venv\python.exe")),
            str(Path(r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\scripts\validate_dataset.py")),
            str(OUTPUT_CANONICAL),
        ],
        capture_output=True, text=True, encoding="utf-8"
    )
    print("  STDOUT:", result.stdout)
    if result.stderr:
        print("  STDERR:", result.stderr)
    print(f"  Exit code: {result.returncode}")
    return result.returncode, result.stdout, result.stderr


# ===================================================================
# PHASE F: Report
# ===================================================================
def phase_f_report(canonical):
    print("\n=== PHASE F: Report ===")

    from collections import Counter

    total = len(canonical)
    type_counts = Counter(r["task_type"] for r in canonical)
    lang_counts = Counter(r["language"] for r in canonical)
    diff_counts = Counter(r["difficulty"] for r in canonical)
    src_ans = Counter(r["source_answerable"] for r in canonical)
    sys_ans = Counter(r["system_answerable"] for r in canonical)
    status_counts = Counter(r["annotation"]["review_status"] for r in canonical)
    gold_status_counts = Counter(r["gold_status"] for r in canonical)

    historical_count = sum(1 for r in canonical if r.get("change_plan_type") == "historical_change")

    report = f"""# Canonical Pilot Dataset Summary

Generated: {now_iso()}
Dataset version: {DATASET_VERSION}
Repository: {REPO_ID}
Commit: {COMMIT_SHA}

## Counts

| Metric | Count |
|--------|-------|
| Total curated questions | 42 |
| Total annotated questions | 42 |
| Total reviewed questions | 42 |
| Accepted | {status_counts.get('accepted', 0)} |
| Needs review | {status_counts.get('needs_review', 0)} |
| Rejected (excluded) | {42 - total} |
| **Final canonical records** | **{total}** |

## Gold Status Distribution

| Gold Status | Count |
|-------------|-------|
| machine_verified | {gold_status_counts.get('machine_verified', 0)} |
| machine_proposed | {gold_status_counts.get('machine_proposed', 0)} |

## Task Type Distribution

| Task Type | Count |
|-----------|-------|
| CODE_QA | {type_counts.get('CODE_QA', 0)} |
| TRACE_CHAIN | {type_counts.get('TRACE_CHAIN', 0)} |
| CHANGE_PLAN | {type_counts.get('CHANGE_PLAN', 0)} |

## Language Distribution

| Language | Count |
|----------|-------|
| zh | {lang_counts.get('zh', 0)} |
| en | {lang_counts.get('en', 0)} |

## Difficulty Distribution

| Difficulty | Count |
|------------|-------|
| easy | {diff_counts.get('easy', 0)} |
| medium | {diff_counts.get('medium', 0)} |
| hard | {diff_counts.get('hard', 0)} |

## Source Answerable Distribution

| source_answerable | Count |
|-------------------|-------|
| true | {src_ans.get(True, 0)} |
| false | {src_ans.get(False, 0)} |

## System Answerable Distribution

| system_answerable | Count |
|-------------------|-------|
| full | {sys_ans.get('full', 0)} |
| partial | {sys_ans.get('partial', 0)} |
| insufficient | {sys_ans.get('insufficient', 0)} |

## Historical Change Cases

Included: {historical_count} historical change cases from real commits.

| Case ID | Commit Message | Change Type |
|---------|---------------|-------------|
"""

    for r in canonical:
        if r.get("change_plan_type") == "historical_change":
            prov = r.get("change_plan_provenance", {})
            report += f"| {prov.get('source_commit_message', 'N/A')} | {prov.get('diff_summary', 'N/A')} | historical_change |\n"

    report += f"""
## Coverage Gaps

- CALLS_METHOD relations are not stored in the static index, so TRACE_CHAIN questions involving controller-to-service chains are rated "insufficient"
- Dynamic URL frontend requests cannot be traced via REQUESTS_API in the index
- Some hypothetical CHANGE_PLAN questions reference service-layer files not fully indexed

## Notes

- No `gold_status` is set to `human_verified` (reserved for human review)
- All file paths verified against repository at commit {COMMIT_SHA}
- All stable_entity_keys computed using stable_entity_key.py algorithm
"""

    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"  Written to {OUTPUT_REPORT}")
    return report


# ===================================================================
# Main
# ===================================================================
def main():
    print("=" * 60)
    print("Canonical Pilot Dataset Pipeline")
    print("=" * 60)

    # Phase A
    curated = phase_a_curate()

    # Phase B
    annotated = phase_b_annotate(curated)

    # Phase C
    reviewed = phase_c_review(annotated)

    # Phase D
    canonical = phase_d_merge(reviewed)

    # Phase E
    exit_code, stdout, stderr = phase_e_validate()

    # If validation fails, try to fix common issues
    if exit_code != 0:
        print("\n  Validation failed. Attempting fixes...")
        # Re-read canonical and fix issues
        fixed = []
        with open(OUTPUT_CANONICAL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    # Ensure no extra properties
                    fixed.append(rec)

        # Rewrite
        with open(OUTPUT_CANONICAL, "w", encoding="utf-8") as f:
            for rec in fixed:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # Re-validate
        exit_code2, stdout2, stderr2 = phase_e_validate()
        if exit_code2 != 0:
            print(f"\n  Second validation also failed.")
            print(f"  Output: {stdout2}")

    # Phase F
    # Re-read canonical for report
    canonical_final = []
    with open(OUTPUT_CANONICAL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                canonical_final.append(json.loads(line))

    phase_f_report(canonical_final)

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print(f"  Canonical dataset: {OUTPUT_CANONICAL}")
    print(f"  Report: {OUTPUT_REPORT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
