# Fusion Weight Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select and adopt a more effective vector/keyword fusion ratio using a predeclared coarse grid, strict artifact validation, and robustness diagnostics.

**Architecture:** Extend the evaluation runner with explicitly selected weight-sweep variants while preserving its frozen default schedule. Add a dedicated fail-closed sweep metrics script that applies the existing file-gold contract, hard gates, grouped metrics, bootstrap diagnostics, and deterministic winner selection. Change the product constant only after independent result approval.

**Tech Stack:** Python 3.11, SQLAlchemy/SQLite, local Qdrant, pytest, JSONL evaluation artifacts.

---

### Task 1: Add opt-in sweep variants

**Files:**
- Modify: `evaluation/runners/stage2b_retrieval.py`
- Modify: `evaluation/scripts/tests/test_stage2b_retrieval.py`

- [ ] **Step 1: Write failing tests**

Add tests that require `W60`, `W65`, `W70`, `W75`, `W80`, `W85`, `W90`,
and `W95` to resolve to complementary weighted variants, while
`tuple(VARIANTS)` remains the frozen nine-variant default. Assert that explicit
selection accepts `B2,W60,...,W95`, rejects duplicates/unknown names, and puts
the exact selected weights into the config fingerprint.

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\backend\.venv\python.exe -m pytest evaluation\scripts\tests\test_stage2b_retrieval.py -q
```

Expected: failures for unknown `W*` variants and missing sweep config.

- [ ] **Step 3: Implement the opt-in registry**

Keep `VARIANTS` unchanged and add:

```python
WEIGHT_SWEEP_VARIANTS = {
    f"W{int(weight * 100):02d}": Variant(
        vector_weight=weight,
        keyword_weight=round(1.0 - weight, 2),
    )
    for weight in (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
}

def variant_by_name(name: str) -> Variant:
    return (VARIANTS | WEIGHT_SWEEP_VARIANTS)[name]
```

Use the combined registry only for explicit parsing, evaluation, and effective
config serialization. Defaults and full Stage 2B behavior remain based on
`VARIANTS` alone.

- [ ] **Step 4: Verify GREEN**

Run the focused test file and the full evaluation test suite. Expected: all
tests pass and no provider call is made.

### Task 2: Build fail-closed sweep metrics and selection

**Files:**
- Create: `evaluation/scripts/compute_fusion_weight_sweep.py`
- Create: `evaluation/scripts/tests/test_compute_fusion_weight_sweep.py`

- [ ] **Step 1: Write failing metric-contract tests**

Fixtures must cover the exact `36 questions × 9 variants = 324` schedule,
identity consistency, all-success status, complete branch diagnostics for
weighted variants, and closed provider ledgers. The CLI requires the approved
previous-run metadata as `--reference-metadata` and the actual provider ledger
directory as `--ledger-dir`. Corrupt one condition at a time and assert a
`ValueError`.

- [ ] **Step 2: Write failing selection tests**

Use synthetic per-case results to prove:

```python
assert select_weight(candidates).name == "W80"
```

when W80 ties the best Recall@5, has the best MRR, preserves Recall@10, and has
no language/task Recall@5 regression. Also prove a higher aggregate-MRR weight
is rejected when a subgroup Recall@5 falls below W70.

- [ ] **Step 3: Verify RED**

Run the new test file. Expected: import failure because the script does not yet
exist.

- [ ] **Step 4: Implement deterministic metrics**

Reuse the canonical case filtering and gold-file rules from
`compute_stage2b_metrics.py`. Report Recall@1/5/10, MRR, zero-hit, first-correct
rank, and language/task/difficulty groups for B2 and every `W*` variant.

- [ ] **Step 5: Implement the hard gates and selector**

First reject the run if B2 Recall@10, W70 Recall@5, or W70 MRR is below the
frozen 0.9815, 0.9722, or 0.8488 values. Reject candidates below the absolute
Recall@10/Recall@5 floors, without an MRR or Recall@5 improvement over W70, or
with any language/task Recall@5 regression.
Sort eligible candidates by:

```python
(
    -recall_at_5,
    -mrr,
    -recall_at_1,
    abs(vector_weight - 0.70),
)
```

- [ ] **Step 6: Add robustness diagnostics**

Use `random.Random(20260717)` for 10,000 case-level bootstrap resamples. Report
the resampling frequency with which each candidate's MRR and Recall@5 are at
least W70, plus leave-one-case-out winner counts. These values are diagnostics,
not posterior probabilities, and do not override hard gates.

For leave-one-case-out only, disable the full 27-case absolute numeric floors;
recompute the relative B2/W70, language/task, improvement, and ordering rules on
the remaining 26 cases. Report this denominator-specific exception explicitly.

- [ ] **Step 7: Verify actual ledgers and write atomically**

Replay `<ledger-dir>/<run_id>/embedding.jsonl` and `rewrite_llm.jsonl` without
modifying them. Require complete paired attempts, zero failures/pending events,
and exact agreement with metadata counters. Reject output aliases with any
input, write through a same-directory temporary file, `flush`/`fsync`, then
`os.replace`.

- [ ] **Step 8: Verify GREEN**

Run the new tests, all evaluation tests, and `compileall`. Expected: zero
failures.

### Task 3: Run the isolated real sweep

**Files:**
- Create: `evaluation/results/raw/fusion_weight_sweep_retrieval.jsonl`
- Create: `evaluation/results/raw/fusion_weight_sweep_retrieval.metadata.json`
- Create: `evaluation/results/metrics/fusion_weight_sweep_metrics.json`

- [ ] **Step 1: Run the selected schedule**

Use the verified independent Qdrant path and a new ledger/output identity:

```powershell
.\backend\.venv\python.exe evaluation\runners\stage2b_retrieval.py `
  --phase all --rebuild --env-file backend\.env `
  --db evaluation\runtime\pilot\rca_eval.db `
  --qdrant-path evaluation\runtime\pilot\fusion_weight_sweep_qdrant `
  --dataset evaluation\datasets\pilot-current.jsonl `
  --dataset-sha 86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c `
  --repo-commit 41720e624c5a668c7d3777835e4c87095a7a1dfd `
  --snapshot evaluation\runtime\pilot\snapshot-v3\manifest.json `
  --variants B2,W60,W65,W70,W75,W80,W85,W90,W95 `
  --output evaluation\results\raw\fusion_weight_sweep_retrieval.jsonl `
  --metadata evaluation\results\raw\fusion_weight_sweep_retrieval.metadata.json `
  --ledger-dir evaluation\runtime\pilot\fusion_weight_sweep_provider_ledgers
```

- [ ] **Step 2: Validate and compute metrics**

Run `compute_fusion_weight_sweep.py` with the frozen dataset, raw, metadata,
snapshot attestation, and a new metrics output. Expected: exact 324 records,
zero failed/pending/unconfirmed/orphan calls, a matching approved reference
configuration, and one selected ratio.

### Task 4: Independent result audit

**Files:**
- Review the Task 3 raw, metadata, ledgers, and metrics.

- [ ] **Step 1: Dispatch an independent data reviewer**

Require a fresh recomputation from raw, per-group gate verification, per-case
rank-change analysis, bootstrap/leave-one-out verification, provider accounting,
and a leakage scan. Do not accept metrics copied from the generated summary.

- [ ] **Step 2: Resolve every Critical or Major issue**

If the reviewer rejects the run, fix the runner/metrics contract test-first and
rerun under a new identity. Do not edit raw results manually.

### Task 5: Adopt the approved production weights

**Files:**
- Modify: `backend/app/retrieval/hybrid_search.py`
- Modify: `backend/tests/unit/test_hybrid_search.py`
- Modify: `evaluation/reports/hybrid-fusion-weight-selection-report.md`

- [ ] **Step 1: Write a failing product test**

Update the characterization test to assert the independently approved weights
and demonstrate a keyword-only candidate can still enter Top-K. Run it and
verify failure against 0.7/0.3.

- [ ] **Step 2: Introduce named constants**

Replace inline literals with named `HYBRID_VECTOR_WEIGHT` and
`HYBRID_KEYWORD_WEIGHT` constants whose exact numeric values equal the approved
metrics artifact's `selected.vector_weight` and `selected.keyword_weight`.
Assert both constants in the product characterization test and assert their sum
is 1.0. Use the constants in `fuse_search_hits`; do not change normalization,
fallback, sorting, or schemas.

- [ ] **Step 3: Verify product and evaluation regressions**

Run the full backend and evaluation suites plus `compileall` and
`git diff --check`. Expected: zero failures.

- [ ] **Step 4: Document the evidence and limits**

The report must include the full grid, hard-gate outcome, selected ratio,
per-case improvements/regressions, robustness diagnostics, provider accounting,
artifact hashes, and the single-repository development-Pilot limitation.

No commit or push is performed without explicit user authorization.
