"""
Split pilot.jsonl into pilot-current.jsonl (36 records) and historical-prepared.jsonl (6 records).
Apply all required transformations to each subset.

**STATUS: legacy -- one-time migration script, already executed**

This script was run once to split the 42-record canonical dataset into:
  - pilot-current.jsonl (36 synthetic questions)
  - historical-prepared.jsonl (6 historical change cases)

It contains hardcoded absolute paths (F:\\LIUQINGYUN\\ResearchCode_Agent) and
should NOT be re-run unless the dataset needs to be re-split from scratch.
The split has already been completed and the output files exist.
"""

import json
import hashlib
import subprocess
import sys
import re
import unicodedata
from pathlib import Path
from copy import deepcopy

# Constants
BASE_DIR = Path(r"F:\LIUQINGYUN\ResearchCode_Agent")
PILOT_JSONL = BASE_DIR / "evaluation" / "datasets" / "pilot.jsonl"
PILOT_CURRENT_JSONL = BASE_DIR / "evaluation" / "datasets" / "pilot-current.jsonl"
HISTORICAL_PREPARED_JSONL = BASE_DIR / "evaluation" / "datasets" / "historical-prepared.jsonl"
HISTORICAL_CASES_JSON = BASE_DIR / "evaluation" / "annotations" / "proposed" / "historical_change_cases.json"
RUOYI_WORKSPACE = BASE_DIR / "evaluation" / "workspaces" / "ruoyi-vue"
HEAD_SHA = "41720e624c5a668c7d3777835e4c87095a7a1dfd"


def is_cjk(char):
    """Check if a character is CJK (Chinese/Japanese/Korean)."""
    cp = ord(char)
    return (
        (0x4E00 <= cp <= 0x9FFF) or     # CJK Unified Ideographs
        (0x3400 <= cp <= 0x4DBF) or     # CJK Unified Ideographs Extension A
        (0x20000 <= cp <= 0x2A6DF) or   # Extension B
        (0x2A700 <= cp <= 0x2B73F) or   # Extension C
        (0x2B740 <= cp <= 0x2B81F) or   # Extension D
        (0x2B820 <= cp <= 0x2CEAF) or   # Extension E
        (0xF900 <= cp <= 0xFAFF) or     # CJK Compatibility Ideographs
        (0x2F800 <= cp <= 0x2FA1F) or   # CJK Compatibility Ideographs Supplement
        (0x3000 <= cp <= 0x303F) or     # CJK Symbols and Punctuation
        (0xFF00 <= cp <= 0xFFEF) or     # Halfwidth and Fullwidth Forms
        (0x3040 <= cp <= 0x309F) or     # Hiragana
        (0x30A0 <= cp <= 0x30FF) or     # Katakana
        (0xAC00 <= cp <= 0xD7AF)        # Hangul Syllables
    )


def detect_language(question_text):
    """Detect language based on CJK character ratio.
    Returns 'zh' if >= 20% CJK, 'en' otherwise.
    """
    if not question_text:
        return "en"
    # Count only non-whitespace, non-punctuation characters for language detection
    chars = [c for c in question_text if c.strip() and not unicodedata.category(c).startswith('P')]
    if not chars:
        return "en"
    cjk_count = sum(1 for c in chars if is_cjk(c))
    ratio = cjk_count / len(chars)
    return "zh" if ratio >= 0.2 else "en"


def git_show_exists(commit_sha, file_path):
    """Check if a file exists at a given commit using git show."""
    try:
        result = subprocess.run(
            ["git", "show", f"{commit_sha}:{file_path}"],
            capture_output=True,
            cwd=str(RUOYI_WORKSPACE),
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  WARNING: git show failed for {commit_sha}:{file_path}: {e}")
        return None  # Unknown


def load_records():
    """Load all records from pilot.jsonl."""
    records = []
    with open(PILOT_JSONL, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"ERROR: Failed to parse line {i}: {e}")
                sys.exit(1)
    print(f"Loaded {len(records)} records from pilot.jsonl")
    return records


def load_historical_cases():
    """Load historical change cases and build case_id -> case mapping."""
    with open(HISTORICAL_CASES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    cases = {}
    for case in data["cases"]:
        cases[case["case_id"]] = case
    print(f"Loaded {len(cases)} historical cases")
    return cases


def build_hc_mapping(records, historical_cases):
    """Map record index (0-based) to HC case by matching base_commit_sha in change_plan_provenance."""
    mapping = {}  # record_index -> case_id
    for idx, rec in enumerate(records):
        if idx < 36:
            continue
        prov = rec.get("change_plan_provenance", {})
        base_sha = prov.get("base_commit_sha", "")
        # Find matching case
        for case_id, case in historical_cases.items():
            if case["base_commit_sha"] == base_sha:
                mapping[idx] = case_id
                break
        if idx not in mapping:
            print(f"  WARNING: No matching HC case for record {idx+1} (base_sha={base_sha})")
    return mapping


def process_current_records(records):
    """Process records 0-35 for pilot-current.jsonl."""
    current = []
    for i in range(36):
        rec = deepcopy(records[i])
        # 1. Add execution_status
        rec["execution_status"] = "executable"
        # 2. Ensure commit_sha = HEAD
        rec["commit_sha"] = HEAD_SHA
        current.append(rec)
    print(f"Processed {len(current)} current records")
    return current


def process_historical_records(records, historical_cases, hc_mapping):
    """Process records 36-41 for historical-prepared.jsonl."""
    historical = []
    language_fixes = []
    file_existence_results = {}

    for i in range(36, 42):
        rec = deepcopy(records[i])
        rec_idx = i
        case_id = hc_mapping.get(i)
        case = historical_cases.get(case_id, {}) if case_id else {}
        base_sha = case.get("base_commit_sha", rec.get("change_plan_provenance", {}).get("base_commit_sha", ""))

        print(f"\n  Processing record {i+1} ({rec['question_id']}), HC={case_id}, base={base_sha[:12]}")

        # 1. Set commit_sha to base_commit_sha
        rec["commit_sha"] = base_sha

        # 2. Set execution_status
        rec["execution_status"] = "prepared_not_executed"

        # 3. Set gold_status
        old_gold_status = rec.get("gold_status")
        rec["gold_status"] = "machine_proposed"
        if old_gold_status != "machine_proposed":
            print(f"    gold_status: {old_gold_status} -> machine_proposed")

        # 4. Set system_answerable
        old_system_answerable = rec.get("system_answerable")
        rec["system_answerable"] = "insufficient"
        if old_system_answerable != "insufficient":
            print(f"    system_answerable: {old_system_answerable} -> insufficient")

        # 5. Fix language field
        question = rec.get("question", "")
        detected_lang = detect_language(question)
        old_lang = rec.get("language")
        if old_lang != detected_lang:
            language_fixes.append({
                "question_id": rec["question_id"],
                "old": old_lang,
                "new": detected_lang,
                "question_preview": question[:60] + "..."
            })
            print(f"    language: {old_lang} -> {detected_lang} (question: {question[:50]}...)")
        rec["language"] = detected_lang

        # 6. Add file_existed_at_base to gold_files
        gold_files = rec.get("gold_files", [])
        new_gold_files = []
        files_not_at_base = set()

        for gf in gold_files:
            fp = gf["file_path"]
            exists = git_show_exists(base_sha, fp)
            gf_copy = dict(gf)

            if exists is True:
                gf_copy["file_existed_at_base"] = True
                file_existence_results.setdefault(rec["question_id"], {})["existed"] = \
                    file_existence_results.setdefault(rec["question_id"], {}).get("existed", 0) + 1
                print(f"    file {fp}: existed at base")
            elif exists is False:
                gf_copy["file_existed_at_base"] = False
                files_not_at_base.add(fp)
                file_existence_results.setdefault(rec["question_id"], {})["new"] = \
                    file_existence_results.setdefault(rec["question_id"], {}).get("new", 0) + 1
                print(f"    file {fp}: NEW (not at base)")
            else:
                # Unknown - default to True (assume existed, safer)
                gf_copy["file_existed_at_base"] = True
                print(f"    file {fp}: UNKNOWN (defaulting to existed)")

            new_gold_files.append(gf_copy)

        rec["gold_files"] = new_gold_files

        # 7. Remove gold_entities that reference files only existing at target/HEAD (not at base)
        gold_entities = rec.get("gold_entities", [])
        filtered_entities = []
        removed_entity_count = 0

        for ge in gold_entities:
            fp = ge.get("file_path", "")
            if fp in files_not_at_base:
                removed_entity_count += 1
                print(f"    Removed gold_entity referencing new file: {ge.get('qualified_name', fp)}")
            else:
                # Check if the entity's file exists at base
                if fp and git_show_exists(base_sha, fp) is False:
                    removed_entity_count += 1
                    files_not_at_base.add(fp)
                    print(f"    Removed gold_entity referencing non-existent file: {ge.get('qualified_name', fp)}")
                else:
                    filtered_entities.append(ge)

        rec["gold_entities"] = filtered_entities
        if removed_entity_count > 0:
            print(f"    Removed {removed_entity_count} gold_entities referencing files not at base")

        # 8. Ensure required_claims don't reference implementation details only visible in target diff
        # We check if required_claims reference files that don't exist at base
        required_claims = rec.get("required_claims", [])
        filtered_claims = []
        for claim in required_claims:
            evidence_file = claim.get("evidence_file", "")
            # If the claim's evidence file doesn't exist at base, it's a target-only detail
            if evidence_file in files_not_at_base:
                print(f"    Removed required_claim referencing new file: {claim.get('claim', '')[:60]}...")
                continue
            # Also check evidence_ranges
            evidence_ranges = claim.get("evidence_ranges", [])
            skip_claim = False
            for er in evidence_ranges:
                er_file = er.get("file_path", "")
                if er_file in files_not_at_base:
                    skip_claim = True
                    break
            if skip_claim:
                print(f"    Removed required_claim with evidence in new file: {claim.get('claim', '')[:60]}...")
                continue
            filtered_claims.append(claim)
        rec["required_claims"] = filtered_claims

        historical.append(rec)

    print(f"\nProcessed {len(historical)} historical records")
    print(f"Language fixes: {len(language_fixes)}")
    for lf in language_fixes:
        print(f"  {lf['question_id']}: {lf['old']} -> {lf['new']}")

    return historical, language_fixes, file_existence_results


def write_jsonl(records, path):
    """Write records to a JSONL file."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} records to {path}")


def compute_sha256(path):
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def print_statistics(current_records, historical_records, language_fixes, file_existence_results):
    """Print comprehensive statistics."""
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)

    # pilot-current statistics
    print("\n--- pilot-current.jsonl ---")
    print(f"Total records: {len(current_records)}")

    # Distribution by task_type
    task_types = {}
    for r in current_records:
        tt = r.get("task_type", "unknown")
        task_types[tt] = task_types.get(tt, 0) + 1
    print(f"By task_type: {dict(sorted(task_types.items()))}")

    # Distribution by language
    languages = {}
    for r in current_records:
        lang = r.get("language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1
    print(f"By language: {dict(sorted(languages.items()))}")

    # Distribution by difficulty
    difficulties = {}
    for r in current_records:
        d = r.get("difficulty", "unknown")
        difficulties[d] = difficulties.get(d, 0) + 1
    print(f"By difficulty: {dict(sorted(difficulties.items()))}")

    # Distribution by source_answerable
    source_ans = {}
    for r in current_records:
        sa = r.get("source_answerable", "unknown")
        source_ans[str(sa)] = source_ans.get(str(sa), 0) + 1
    print(f"By source_answerable: {dict(sorted(source_ans.items()))}")

    # Distribution by system_answerable
    sys_ans = {}
    for r in current_records:
        sa = r.get("system_answerable", "unknown")
        sys_ans[sa] = sys_ans.get(sa, 0) + 1
    print(f"By system_answerable: {dict(sorted(sys_ans.items()))}")

    # Confirm all have execution_status=executable and commit_sha=HEAD
    all_executable = all(r.get("execution_status") == "executable" for r in current_records)
    all_head = all(r.get("commit_sha") == HEAD_SHA for r in current_records)
    print(f"All execution_status=executable: {all_executable}")
    print(f"All commit_sha=HEAD: {all_head}")

    # Confirm NO historical records
    historical_in_current = [r for r in current_records if r.get("change_plan_type") == "historical_change"]
    print(f"Historical records in pilot-current: {len(historical_in_current)} (should be 0)")

    # historical-prepared statistics
    print("\n--- historical-prepared.jsonl ---")
    print(f"Total records: {len(historical_records)}")

    # Base SHAs
    base_shas = {}
    for r in historical_records:
        sha = r.get("commit_sha", "unknown")
        base_shas[r["question_id"]] = sha[:12]
    print(f"Base SHAs: {base_shas}")

    # Confirm NO HEAD commit_sha
    head_in_historical = [r for r in historical_records if r.get("commit_sha") == HEAD_SHA]
    print(f"HEAD commit_sha in historical-prepared: {len(head_in_historical)} (should be 0)")

    # Language fixes
    print(f"Language fixes applied: {len(language_fixes)}")
    for lf in language_fixes:
        print(f"  {lf['question_id']}: {lf['old']} -> {lf['new']}")

    # Distribution by language
    hist_languages = {}
    for r in historical_records:
        lang = r.get("language", "unknown")
        hist_languages[lang] = hist_languages.get(lang, 0) + 1
    print(f"By language: {dict(sorted(hist_languages.items()))}")

    # file_existed_at_base counts
    total_existed = 0
    total_new = 0
    for qid, counts in file_existence_results.items():
        e = counts.get("existed", 0)
        n = counts.get("new", 0)
        total_existed += e
        total_new += n
        print(f"  {qid}: existed_at_base={e}, new_files={n}")
    print(f"Total files: existed_at_base={total_existed}, new_files={total_new}")

    # Confirm all have correct execution_status and gold_status
    all_prepared = all(r.get("execution_status") == "prepared_not_executed" for r in historical_records)
    all_proposed = all(r.get("gold_status") == "machine_proposed" for r in historical_records)
    all_insufficient = all(r.get("system_answerable") == "insufficient" for r in historical_records)
    print(f"All execution_status=prepared_not_executed: {all_prepared}")
    print(f"All gold_status=machine_proposed: {all_proposed}")
    print(f"All system_answerable=insufficient: {all_insufficient}")


def main():
    print("=" * 80)
    print("Splitting pilot.jsonl into pilot-current.jsonl and historical-prepared.jsonl")
    print("=" * 80)

    # Load data
    records = load_records()
    if len(records) != 42:
        print(f"ERROR: Expected 42 records, got {len(records)}")
        sys.exit(1)

    historical_cases = load_historical_cases()
    hc_mapping = build_hc_mapping(records, historical_cases)

    # Process current records (0-35)
    print("\n--- Processing current records (0001-0036) ---")
    current_records = process_current_records(records)

    # Process historical records (36-41)
    print("\n--- Processing historical records (0037-0042) ---")
    historical_records, language_fixes, file_existence_results = \
        process_historical_records(records, historical_cases, hc_mapping)

    # Write output files
    print("\n--- Writing output files ---")
    write_jsonl(current_records, PILOT_CURRENT_JSONL)
    write_jsonl(historical_records, HISTORICAL_PREPARED_JSONL)

    # Step 5: Update pilot.jsonl = pilot-current.jsonl
    print("\n--- Updating pilot.jsonl ---")
    write_jsonl(current_records, PILOT_JSONL)
    print("pilot.jsonl updated to match pilot-current.jsonl")

    # Step 7: Compute SHA-256
    sha256 = compute_sha256(PILOT_CURRENT_JSONL)
    print(f"\n--- SHA-256 of pilot-current.jsonl ---")
    print(f"{sha256}")

    # Step 8: Statistics
    print_statistics(current_records, historical_records, language_fixes, file_existence_results)

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
