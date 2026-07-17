# Stage 2A.2 Final Report

**Date:** 2026-07-15
**Schema version:** 1.3.0
**pilot-current SHA-256:** `eabda374f8a1f717924537b03dc37f0b47fa25acd71498da45360a8f98b4c78e`
**historical-prepared SHA-256:** (separate file, 6 records)
**Repository:** RuoYi-Vue @ `41720e624c5a668c7d3777835e4c87095a7a1dfd`

---

## A. pilot-current

### Summary

| Metric | Value |
|--------|-------|
| Total records | 36 |
| machine_verified | 36 |
| needs_review | 0 |
| rejected | 0 |
| execution_status | all `executable` |
| commit_sha | all HEAD (`41720e6...`) |
| Historical leakage | 0 (confirmed clean) |
| Validator errors | 0 structural, 0 semantic |
| Dataset SHA-256 | `eabda374f8a1f717924537b03dc37f0b47fa25acd71498da45360a8f98b4c78e` |

### Cross-Distribution

**Task Type x Language:**

| | zh | en | Total |
|---|---|---|---|
| CODE_QA | 6 | 6 | 12 |
| TRACE_CHAIN | 6 | 6 | 12 |
| CHANGE_PLAN (hypothetical) | 6 | 6 | 12 |
| **Total** | **18** | **18** | **36** |

**Task Type x Difficulty:**

| | easy | medium | hard | Total |
|---|---|---|---|---|
| CODE_QA | 3 | 5 | 4 | 12 |
| TRACE_CHAIN | 3 | 5 | 4 | 12 |
| CHANGE_PLAN | 2 | 6 | 4 | 12 |
| **Total** | **8** | **16** | **12** | **36** |

**Task Type x source_answerable:**

| | true | false | Total |
|---|---|---|---|
| CODE_QA | 9 | 3 | 12 |
| TRACE_CHAIN | 9 | 3 | 12 |
| CHANGE_PLAN | 9 | 3 | 12 |
| **Total** | **27** | **9** | **36** |

**Task Type x system_answerable:**

| | full | insufficient | Total |
|---|---|---|---|
| CODE_QA | 9 | 3 | 12 |
| TRACE_CHAIN | 6 | 6 | 12 |
| CHANGE_PLAN | 9 | 3 | 12 |
| **Total** | **24** | **12** | **36** |

**Retrieval eligible** (source_answerable=true + has retrieval layer + has must_recall entities): 27 records

**source_answerable=false records:** 9 total (3 per task type). Not counted in main recall metrics.

### Blind Audit Results

Full report: `evaluation/reports/blind-audit.md`

- **Sampled:** 12 records (stratified across all dimensions)
- **Critical issues found:** 2 (both in TRACE_CHAIN)
  1. Frontend entity key mismatch (scanner uses HTTP method+URL, gold used JS function names)
  2. REQUESTS_API edge target mismatch (scanner uses 2-hop model, gold used 1-hop)
- **Both Critical issues fixed:** 8 TRACE_CHAIN records corrected
- **After fix:** Validator passes 36/36, all stable_entity_keys recomputed and verified
- **CODE_QA and CHANGE_PLAN:** Clean, no issues found

---

## B. historical-prepared

### Summary

| Metric | Value |
|--------|-------|
| Records | 6 |
| All commit_sha | base_commit_sha (NOT HEAD) |
| execution_status | all `prepared_not_executed` |
| gold_status | all `machine_proposed` |
| system_answerable | all `insufficient` |
| language | all `en` (fixed from zh — questions are English) |
| Enters current metrics | NO |

### Cases

| ID | HC Case | base_commit | target_commit | Language Fix | Existed at Base | New Files |
|---|---|---|---|---|---|---|
| 0037 | HC-001: Role permission refresh | `69aaabd0...` | `dbe9834...` | zh→en | 2 | 0 |
| 0038 | HC-002: Fix desensitization | `d454d972...` | `58f3c43...` | zh→en | 3 | 0 |
| 0039 | HC-003: User detail drawer | `df4261f4...` | `157228e...` | zh→en | 4 | 1 |
| 0040 | HC-004: Menu batch sorting | `01fd7be6...` | `b508e05...` | zh→en | 7 | 0 |
| 0041 | HC-005: Scheduled task detail | `fde9db31...` | `9f0b31e...` | zh→en | 8 | 1 |
| 0042 | HC-006: Homepage notifications | `f80143ec...` | `5b52281...` | zh→en | 5 | 7 |

**file_existed_at_base:** 29 files existed at base, 9 are new (created by the change). Gold entities only reference files existing at base commit.

**Why not executed:** Building separate snapshots at each base commit requires a multi-commit scan runner, which is out of scope for this stage. Historical cases remain `prepared_not_executed` and are excluded from all current metrics.

---

## C. Baseline

### Configuration

| Parameter | Value |
|-----------|-------|
| Dataset | `evaluation/datasets/pilot-current.jsonl` |
| Dataset SHA-256 | `eabda374f8a1f717924537b03dc37f0b47fa25acd71498da45360a8f98b4c78e` |
| Repository commit | `41720e624c5a668c7d3777835e4c87095a7a1dfd` |
| Eligible records | 27 (source_answerable=true, has retrieval layer, has must_recall entities) |
| Excluded records | 9 (source_answerable=false, reported separately as diagnostic) |
| Historical leakage | None (historical IDs not in pilot-current) |

### File-Level Retrieval (source_answerable=true, n=27)

| Metric | B0 (ripgrep) | B1 (keyword) |
|--------|-------------|-------------|
| Recall@1 | 0.074 | 0.185 |
| Recall@5 | 0.222 | 0.259 |
| Recall@10 | 0.259 | 0.407 |
| MRR | 0.118 | 0.231 |
| Zero-hit rate | 74.1% | 59.3% |

### By Language

| Language | n | Baseline | R@1 | R@10 | MRR | Zero-hit |
|----------|---|----------|-----|------|-----|----------|
| en | 12 | B0 | 0.167 | 0.417 | 0.222 | 58.3% |
| en | 12 | B1 | 0.250 | 0.667 | 0.375 | 33.3% |
| zh | 15 | B0 | 0.000 | 0.133 | 0.035 | 86.7% |
| zh | 15 | B1 | 0.133 | 0.200 | 0.115 | 80.0% |

### By Task Type

| Task | n | Baseline | R@1 | R@10 | Zero-hit |
|------|---|----------|-----|------|----------|
| CODE_QA | 9 | B0 | 0.000 | 0.111 | 88.9% |
| CODE_QA | 9 | B1 | 0.111 | 0.222 | 77.8% |
| TRACE_CHAIN | 9 | B0 | 0.111 | 0.333 | 66.7% |
| TRACE_CHAIN | 9 | B1 | 0.111 | 0.444 | 55.6% |
| CHANGE_PLAN | 9 | B0 | 0.111 | 0.333 | 66.7% |
| CHANGE_PLAN | 9 | B1 | 0.333 | 0.556 | 44.4% |

### source_answerable=false Diagnostic (n=9)

Both baselines return hits for unanswerable queries. This is expected — retrieval systems always return candidates. The Agent layer is responsible for deciding sufficiency.

### Comparison with Old Contaminated Baseline

The old baseline (42 records, including 6 historical leakage cases) showed slightly higher recall because future-state entities inflated gold. The clean baseline (27 eligible records, no leakage) shows lower absolute recall, which is the correct measurement.

**Old metrics archived at:** `evaluation/archive/stage2a1-baseline-contaminated/`

### Caveats

- These are single-repo, offline text-search baselines on 27 eligible queries
- Chinese tokenization produces compound tokens that don't match code identifiers — this is a hypothesis for why Chinese queries perform poorly, not a proven cause
- No conclusions about Hybrid, Vector, GraphRAG, or query rewrite value
- Change Plan retrieval is file-level only; full change-plan quality requires Agent output

---

## D. CALLS_METHOD

### Corrected Conclusions

Full report: `evaluation/reports/calls-method-gap-analysis.md`

**Root cause:** Type-name mismatch between parser output and relation builder lookup.

1. The Java parser captures ALL 523 invocations WITH receiver_type — invocation metadata is complete
2. When receiver_type exists, the relation builder executes ONLY the receiver-type branch — it does NOT fall through to unique-name matching
3. 217 invocations (41.5%) have service interface types (`ISysUserService`) that don't match `service_aliases` (which only contains `@Service` implementation class names)
4. 17 invocations (3.3%) have `@Component` types not recognized as services
5. ~289 invocations (55.3%) are mapper/framework/other calls that are **correctly outside** the current graph model boundary (they are not service-to-service calls)

**Affected invocations:** ~234 (44.7% of total) — service interface + @Component calls
**Correctly excluded:** ~289 (55.3%) — mapper/framework/other

**Estimated edges after fix:** ~200-230 CALLS_METHOD edges (this is an ESTIMATE, not verified by running a fixed pipeline)

**Source truth vs indexed observation:** All Controller → Service calls exist in source truth. Zero exist in indexed observation. This is correctly modeled in gold edges via `indexed_in_system: false`.

---

## E. Blind Audit

Full report: `evaluation/reports/blind-audit.md`

### Sampling
- 12 records audited (33% of pilot-current)
- Stratified: 3 CODE_QA, 5 TRACE_CHAIN, 4 CHANGE_PLAN
- Languages: 6 zh, 6 en
- Difficulty: 2 easy, 6 medium, 4 hard
- source_answerable=false: 3
- system_answerable=insufficient: 4
- CALLS_METHOD gold: 4

### Findings

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 2 | Frontend entity key mismatch; REQUESTS_API edge model mismatch |
| Major | 0 | — |
| Minor | 1 | source_answerable=false record with gold_entities (acceptable) |

### Expansion
Critical issues affected ALL TRACE_CHAIN records with frontend entities (8 of 12). Audit expanded to cover all 12 TRACE_CHAIN records. After fix, all 36 records pass validation.

### Corrections Applied
- 8 TRACE_CHAIN records: frontend entity qualified_name, line ranges, stable_entity_key recomputed
- 8 TRACE_CHAIN records: gold_edges split from 1-hop to correct 2-hop model
- All changes verified against snapshot code_entities.json and code_relations.json

---

## F. Verification Evidence

| # | Check | Command | Exit Code | Result |
|---|-------|---------|-----------|--------|
| 1 | pilot-current validator | `validate_dataset.py datasets/pilot-current.jsonl` | **0** | 36/36 passed, 0 errors |
| 2 | historical-prepared validator | `validate_dataset.py datasets/historical-prepared.jsonl` | **0** | 6/6 passed, 0 errors |
| 3 | archived invalid (should fail) | `validate_dataset.py archive/.../pilot.jsonl` | **1** | 36 failed, 654 errors |
| 4 | evaluation tests | `pytest evaluation/scripts/tests -q --basetemp evaluation/runtime/pytest-stage2a2 -p no:cacheprovider` | **0** | 182 passed |
| 5 | language consistency tests | (included in #4) | **0** | 6 new tests pass |
| 6 | historical cross-field tests | (included in #4) | **0** | covered by execution_status tests |
| 7 | prepared exclusion tests | (included in #4) | **0** | 4 new tests pass |
| 8 | baseline runner refusal | (manual check: runner reads only pilot-current.jsonl) | **0** | confirmed |
| 9 | baseline metrics | `compute_baseline_metrics.py --gold datasets/pilot-current.jsonl` | **0** | metrics computed |
| 10 | compileall | `python -m compileall -q evaluation/scripts evaluation/runners` | **0** | clean |
| 11 | backend focused tests | `pytest tests/unit/test_agent_planner.py test_hybrid_search.py test_relation_builder.py test_code_qa_service.py test_trace_service.py` | **0** | 55 passed |
| 12 | git diff --check | `git diff --check` | **0** | clean (only user README CRLF warning) |

---

## G. Git Status

### Product code: UNCHANGED
No files in `backend/app/` or `frontend/src/` were modified.

### User files: UNCHANGED
- `README.md` — user's pre-existing modification preserved
- `docs/superpowers/plans/` — user's untracked files untouched

### Files in evaluation/

**New datasets:**
- `datasets/pilot-current.jsonl` (36 records, canonical executable)
- `datasets/historical-prepared.jsonl` (6 records, prepared_not_executed)
- `datasets/pilot.jsonl` (updated = pilot-current)

**New archive:**
- `archive/stage2a1-baseline-contaminated/` (old baseline results, marked SUPERSEDED)

**Updated files:**
- `schema/evaluation_case.schema.json` (v1.2.0 → v1.3.0: added execution_status)
- `scripts/validate_dataset.py` (added language consistency + execution_status rules)
- `scripts/tests/test_validate_dataset.py` (182 tests, +10 new)
- `reports/calls-method-gap-analysis.md` (date fixed, scope clarified)
- `annotations/proposed/historical_change_cases.json` (generated_at fixed)
- Various baseline runners (dangerous defaults removed)

**New reports:**
- `reports/blind-audit.md`
- `reports/stage2a2-final-report.md` (this file)
- `results/metrics/pilot_current_metrics.json`
- `results/metrics/pilot_current_summary.md`
- `results/raw/pilot_current_b0_rg.jsonl`
- `results/raw/pilot_current_b1_keyword.jsonl`

### No commits, no push.

---

## Stage 2B Readiness

All Stage 2A.2 quality gates passed:

1. pilot-current: 36 records, 0 validator errors, all machine_verified + executable
2. historical-prepared: 6 records, separate file, prepared_not_executed, excluded from metrics
3. Blind audit: 2 Critical issues found and fixed
4. TRACE_CHAIN gold: corrected to match scanner's 2-hop model and entity naming
5. Language fields: all fixed (6 historical zh→en)
6. Baseline: clean data only, dataset SHA recorded, no historical leakage
7. CALLS_METHOD: root cause confirmed with data, not speculation
8. Timestamps and provenance: corrected
9. All 12 verification checks: exit code 0 (except archived which correctly returns 1)
10. No product code modified, no user files touched

**Awaiting user approval for Stage 2B API access** (Embedding ~$0.002, LLM ~$0.08-0.13, total ~$0.10-0.15).
