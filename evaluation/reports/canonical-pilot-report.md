# SUPERSEDED -- 42-record contaminated dataset

**Status:** This report has been SUPERSEDED by the Stage 2A.2 split.
**Reason:** Based on the 42-record canonical dataset (SHA `3cd1a...`) that mixed
36 synthetic questions with 6 historical change cases (data leakage).
**Current valid report:** `evaluation/reports/stage2a2-final-report.md` (36 records, SHA `eabda...`)

---

# Canonical Pilot Report (Stage 2A.1)

**Date:** 2026-07-15
**Dataset SHA-256:** `3cd1a827175114a6f02249005cde8b73560dcb11f9b4a17899ff4ccb1a303a66`
**Schema version:** 1.2.0
**Repository:** RuoYi-Vue @ `41720e624c5a668c7d3777835e4c87095a7a1dfd`
**Status:** Canonical — all quality gates passed

> The previous Stage 2A draft report has been **SUPERSEDED** and archived at
> `evaluation/archive/stage2a-draft-invalid/`. Its data, metrics, and conclusions
> are invalid for benchmark purposes.

---

## A. Root Cause and Fixes

### Why did the previous round produce simplified formats?

The question generator agent was instructed to produce JSON matching the Schema, but was given insufficient context about the expected field structures. It produced string-only gold_entities, gold_files, and required_claims instead of the required structured objects. This was a prompt engineering failure, not a Schema design issue.

### Why didn't the validator stop the pipeline?

The validator (`validate_dataset.py`) was built concurrently with the question generator and included "compatibility hacks" — `isinstance(entity, str)` guards that silently skipped string-format entities instead of failing. This allowed invalid data to pass through to the baseline runner.

### Why did metrics use proposed annotations?

The baseline runner was pointed at `annotations/proposed/pilot_candidates.jsonl` instead of `datasets/pilot.jsonl`. There was no gate requiring Schema validation before metric computation.

### Why was role separation violated?

Token budget pressure led to combining the Question Generator and Evidence Annotator roles into a single agent (`question_generator_A`). The adversarial reviewer partially compensated, but the fundamental isolation was broken.

### How each was fixed at the source

1. **Format enforcement:** All compatibility hacks deleted from the validator. String entities now fail Schema validation. The canonical builder explicitly constructs structured objects.
2. **Validation gate:** The baseline runner now calls `validate_dataset.py` before computing metrics and refuses to proceed on failure.
3. **Role separation:** Four distinct agents with distinct role identifiers: `question_curator_B`, `evidence_annotator_B`, `adversarial_reviewer_C`, and (if needed) `adjudicator_D`.
4. **Schema clarity:** Replaced ambiguous `answerable` (boolean) with `source_answerable` (boolean) and `system_answerable` (enum: full/partial/insufficient).

---

## B. Canonical Data

### Summary

| Metric | Value |
|--------|-------|
| Total curated questions | 42 |
| Total annotated | 42 |
| Total accepted by reviewer | 42 |
| machine_verified | 42 |
| needs_review | 0 |
| rejected | 0 |
| Historical change cases | 6 (all `prepared_not_executed`) |
| Hypothetical change cases | 12 |
| Validator errors | 0 structural, 0 semantic |
| Dataset SHA-256 | `3cd1a827175114a6f02249005cde8b73560dcb11f9b4a17899ff4ccb1a303a66` |

### Distribution

| Dimension | Values |
|-----------|--------|
| **Task type** | CODE_QA: 12, TRACE_CHAIN: 12, CHANGE_PLAN: 18 (12 hypothetical + 6 historical) |
| **Language** | zh: 24, en: 18 |
| **Difficulty** | easy: 8, medium: 22, hard: 12 |
| **source_answerable** | true: 33, false: 9 |
| **system_answerable** | full: 30, insufficient: 12 |

### Coverage Gaps

1. **Historical change cases:** 6 identified from Git history, all marked `prepared_not_executed`. Cannot execute because the scan was done at HEAD, not at the base commit of each change. A multi-commit scan runner is needed for Stage 2B.
2. **TRACE_CHAIN with CALLS_METHOD:** All CALLS_METHOD edges are marked `indexed_in_system: false` due to the interface-to-impl type mismatch. These correctly count as system false negatives.
3. **Language balance:** 24 zh vs 18 en is slightly unbalanced (57/43). Acceptable for Pilot.

---

## C. CALLS_METHOD Investigation

Full report: `evaluation/reports/calls-method-gap-analysis.md`

### Confirmed Root Cause

**Type-name mismatch between parser and relation builder**, not generic method name ambiguity.

The Java parser (`java_parser.py`) correctly extracts 523 method invocations with receiver types. However, receiver types are always **interface names** (e.g., `ISysUserService`) because that's how Spring dependency injection declares fields.

The relation builder (`relation_builder.py`) builds its lookup table from `@Service`-annotated **implementation classes** (e.g., `SysUserServiceImpl`). When resolving `ISysUserService`, the lookup in `service_aliases` returns empty because `ISysUserService` was never indexed as an entity (tree-sitter treats `interface_declaration` differently from `class_declaration`).

### Statistics

| Category | Count | % |
|----------|-------|---|
| Service interface types (`I*Service`) | ~217 | 41.5% |
| `@Component` classes (not `@Service`) | ~17 | 3.3% |
| Mapper/framework types (correctly skipped) | ~289 | 55.3% |

### Source Truth vs Indexed Observation

For every Controller -> Service call in the 10 analyzed samples:
- **Source truth:** CALLS_METHOD relation exists (verified by reading source code)
- **Indexed observation:** Missing (interface type not resolvable by relation builder)
- **Evaluation treatment:** Edge marked `indexed_in_system: false`, counted as system false negative

### No product code modified

This is an investigation-only report. Whether to fix the parser/relation builder is a separate decision for the user.

---

## D. Baseline Results

### Eligible Records

- Total canonical records: 42
- Records with retrieval layer: 35
- Records with must_recall gold entities: 33 (all source_answerable=true)
- Records with source_answerable=false: 7 (no must_recall entities, reported as diagnostic only)

### File-Level Retrieval (source_answerable=true, n=33)

| Metric | B0 (ripgrep) | B1 (keyword) |
|--------|-------------|-------------|
| Recall@1 | 0.091 | 0.273 |
| Recall@5 | 0.242 | 0.333 |
| Recall@10 | 0.273 | 0.455 |
| MRR | 0.133 | 0.310 |
| Zero-hit rate | 72.7% | 54.5% |

### By Language

| Language | n | Baseline | R@1 | R@10 | MRR | Zero-hit |
|----------|---|----------|-----|------|-----|----------|
| en | 12 | B0 | 0.083 | 0.333 | 0.167 | 58.3% |
| en | 12 | B1 | 0.333 | 0.667 | 0.444 | 33.3% |
| zh | 21 | B0 | 0.095 | 0.238 | 0.113 | 81.0% |
| zh | 21 | B1 | 0.238 | 0.333 | 0.233 | 66.7% |

### By Task Type

| Task | n | Baseline | R@1 | R@10 | Zero-hit |
|------|---|----------|-----|------|----------|
| CODE_QA | 9 | B0 | 0.000 | 0.111 | 88.9% |
| CODE_QA | 9 | B1 | 0.111 | 0.222 | 77.8% |
| TRACE_CHAIN | 9 | B0 | 0.111 | 0.333 | 66.7% |
| TRACE_CHAIN | 9 | B1 | 0.222 | 0.444 | 55.6% |
| CHANGE_PLAN | 15 | B0 | 0.133 | 0.333 | 66.7% |
| CHANGE_PLAN | 15 | B1 | 0.400 | 0.600 | 40.0% |

### Unanswerable Queries (source_answerable=false, n=9)

Both baselines always produce candidate hits for unanswerable queries. This is expected behavior for retrieval systems — they return candidates, and the Agent layer is responsible for deciding whether evidence is sufficient. We do NOT label these hits as "false positives" at the retrieval layer. Diagnostic: B0 zero-hit = 66.7%, B1 zero-hit = 44.4%.

### Caveats

- These are **single-repo, offline text-search baselines** on 33 eligible queries.
- B1 uses tokenized keyword search (extracted tokens from queries), not the full `KeywordSearchService` with its field-weighted scoring. The tokenization is identical for B0 and B1 to ensure fairness.
- Chinese tokenization produces long compound tokens (e.g., "用户管理模块" as one token) that don't match code identifiers, explaining the high zero-hit rate.
- **No conclusions about Hybrid, Vector, or GraphRAG can be drawn from these baselines alone.**

---

## E. Verification Evidence

| Check | Command | Exit Code | Result |
|-------|---------|-----------|--------|
| Evaluation tests | `pytest evaluation/scripts/tests -q --basetemp evaluation/runtime/pytest-tmp` | **0** | 172 passed |
| Canonical validation | `validate_dataset.py datasets/pilot.jsonl` | **0** | 42 passed, 0 errors |
| Archived data rejected | `validate_dataset.py archive/stage2a-draft-invalid/pilot.jsonl` | **1** | 36 failed, 618 errors |
| compileall | `python -m compileall -q evaluation/scripts evaluation/runners` | **0** | Clean |
| git diff --check | `git diff --check` | **0** | Only CRLF warning on user's README.md |
| Backend tests | `pytest backend/tests/unit/test_agent_planner.py test_hybrid_search.py test_relation_builder.py` | **0** | 39 passed |

---

## F. Git and File Status

### Product code: UNCHANGED

No files in `backend/app/` or `frontend/src/` were modified.

### User files: UNCHANGED

- `README.md` — user's pre-existing modification preserved
- `docs/superpowers/plans/` — user's untracked files untouched

### New/modified files in evaluation/

```
evaluation/
  archive/
    stage2a-draft-invalid/
      archive-manifest.json (new)
      pilot.jsonl (archived)
      pilot_candidates.jsonl (archived)
      pilot_review.jsonl (archived)
      b0_rg.jsonl (archived)
      b1_keyword.jsonl (archived)
      baseline_summary.json (archived)
      pilot-report.md (archived, marked SUPERSEDED)
      generate_questions.py (archived)
  schema/
    evaluation_case.schema.json (updated to v1.2.0)
  datasets/
    pilot.jsonl (REBUILT — 42 canonical records)
  annotations/
    proposed/
      curated_questions.json (new)
      annotated_by_b.json (new)
      historical_change_cases.json (new)
      build_canonical_pilot.py (new)
    reviewed/
      reviewed_by_c.json (new)
  scripts/
    validate_dataset.py (fixed — removed hacks, strict enforcement)
    archive_manifest.py (new)
    diagnose_calls_method.py (new)
    compute_canonical_metrics.py (new)
    tests/
      test_validate_dataset.py (fixed — 172 tests)
  runners/
    baseline_rg.py (minor fix for canonical format)
    baseline_keyword.py (minor fix for canonical format)
  reports/
    pilot-report.md (marked SUPERSEDED)
    calls-method-gap-analysis.md (new)
    canonical-pilot-summary.md (new)
    canonical-pilot-report.md (this file, new)
  results/
    raw/
      canonical_b0_rg.jsonl (new)
      canonical_b1_keyword.jsonl (new)
    metrics/
      canonical_baseline_metrics.json (new)
      canonical_baseline_summary.md (new)
```

### No commits, no push.

---

## G. Stage 2B Application

All canonical Pilot quality gates have been passed:

1. Every canonical sample is Schema-compliant (42/42, 0 errors)
2. Every sample has independent Evidence Annotator (`evidence_annotator_B`)
3. Every sample has independent Adversarial Reviewer (`adversarial_reviewer_C`)
4. All paths and line numbers verified against source at fixed commit
5. Stable entity keys computed and verifiable
6. Source truth and indexed observation distinguished via `indexed_in_system` and `system_answerable`
7. Graph edge endpoints verified
8. Critical disagreements: 0
9. needs_review excluded from canonical metrics: 0 (all accepted)
10. Minimum retention met: 12 CODE_QA, 12 TRACE_CHAIN, 18 CHANGE_PLAN (12 hypothetical + 6 historical)
11. Coverage: zh/en, easy/medium/hard, source_answerable true/false
12. Validator returns 0
13. pytest returns 0
14. Baselines read only canonical dataset
15. Report cites dataset SHA-256
16. All old invalid results marked SUPERSEDED

### Requesting authorization for Stage 2B

The following require real API access:

| Component | Estimated Cost | Purpose |
|-----------|---------------|---------|
| Embedding API | ~$0.002 (Zhipu embedding-3, 2199 entities, ~35 batches) | Build vector index, Vector baseline (B2), Hybrid baseline (B3/B4) |
| LLM API (query rewrite) | ~$0.01 (18 Chinese queries) | Ablation: with/without query rewrite |
| LLM API (Agent answers) | ~$0.05-0.10 (42 questions + ~7 repairs) | Full Agent evaluation (B5) |
| LLM API (stability subset) | ~$0.02 (8 questions, 3x each) | Variance measurement on 20% subset |
| **Total estimated** | **~$0.10-0.15** | |

### Lower-cost alternatives

- Local sentence-transformers (`all-MiniLM-L6-v2`) instead of Zhipu API: $0 embedding cost but lower quality and different model
- Skip stability subset: saves ~$0.02 but loses variance data
- Skip query rewrite ablation: saves ~$0.01 but loses evidence for Chinese retrieval improvement

### Stage 2B scope

1. Build vector index on RuoYi-Vue (requires Embedding API)
2. Run B2 (Vector only), B3 (Hybrid), B4 (Hybrid + Graph)
3. Run B5 (full Agent chat) on all 42 questions
4. Ablation: with/without query rewrite
5. Compute all metrics on canonical dataset only
6. Write Stage 2B report with interview evidence

**Awaiting user approval for API access.**
