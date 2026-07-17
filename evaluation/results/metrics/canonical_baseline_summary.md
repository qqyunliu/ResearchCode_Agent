# SUPERSEDED -- CONTAMINATED DATASET (42 records)

**Status:** This file has been SUPERSEDED and archived.
**Reason:** Computed on the old 42-record canonical dataset that included 6
historical change cases mixed with 36 synthetic questions (data leakage).
**Archive location:** `evaluation/archive/stage2a1-baseline-contaminated/canonical_baseline_summary.md`
**Current valid metrics:** `evaluation/results/metrics/pilot_current_summary.md` (36 records)

**This file should be removed from results/metrics/ -- it exists only as a
stale copy that was not cleaned up when the archive was created.**

---

# Canonical Baseline Retrieval Metrics

## Dataset

- **Dataset**: `evaluation/datasets/pilot.jsonl` (canonical)
- **SHA-256**: `3cd1a827175114a6f02249005cde8b73560dcb11f9b4a17899ff4ccb1a303a66`
- **Total records**: 42
- **Eligible records** (machine_verified + accepted + retrieval layer): 42
- **Records with gold files** (must_recall entities): 35
  - source_answerable=true: 33
  - source_answerable=false (diagnostic): 2
- **Records without gold files** (skipped from recall computation): 7
  - All 7 are source_answerable=false with system_answerable=insufficient

## Overall Metrics (source_answerable=true, n=33)

| Metric | B0 (ripgrep) | B1 (keyword) |
|---|---|---|
| Recall@1 | 0.0909 | 0.2727 |
| Recall@5 | 0.2424 | 0.3333 |
| Recall@10 | 0.2727 | 0.4545 |
| MRR | 0.1327 | 0.3100 |
| Zero-hit rate | 0.7273 | 0.5455 |

## Diagnostic Metrics (source_answerable=false, n=2)

| Metric | B0 (ripgrep) | B1 (keyword) |
|---|---|---|
| Recall@1 | 0.0 | 0.0 |
| Recall@5 | 0.0 | 0.0 |
| Recall@10 | 0.0 | 0.0 |
| MRR | 0.0 | 0.0 |
| Zero-hit rate | 1.0 | 1.0 |

Note: These 2 records have must_recall gold entities despite source_answerable=false.
Both baselines returned zero hits for these records. The remaining 7 source_answerable=false
records have no must_recall entities and are excluded from recall computation.

## Grouped Metrics (source_answerable=true only)

### By Language

**English (n=12)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0 | 0.25 |
| Recall@5 | 0.3333 | 0.4167 |
| Recall@10 | 0.4167 | 0.6667 |
| MRR | 0.0981 | 0.3441 |
| Zero-hit rate | 0.5833 | 0.3333 |

**Chinese (n=21)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1429 | 0.2857 |
| Recall@5 | 0.1905 | 0.2857 |
| Recall@10 | 0.1905 | 0.3333 |
| MRR | 0.1524 | 0.2905 |
| Zero-hit rate | 0.8095 | 0.6667 |

### By Difficulty

**Easy (n=8)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0 | 0.0 |
| Recall@5 | 0.0 | 0.25 |
| Recall@10 | 0.0 | 0.25 |
| MRR | 0.0 | 0.0938 |
| Zero-hit rate | 1.0 | 0.75 |

**Medium (n=18)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1667 | 0.5 |
| Recall@5 | 0.3333 | 0.5 |
| Recall@10 | 0.3889 | 0.6111 |
| MRR | 0.2136 | 0.5117 |
| Zero-hit rate | 0.6111 | 0.3889 |

**Hard (n=7)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0 | 0.0 |
| Recall@5 | 0.2857 | 0.0 |
| Recall@10 | 0.2857 | 0.2857 |
| MRR | 0.0762 | 0.0383 |
| Zero-hit rate | 0.7143 | 0.7143 |

### By Task Type

**CODE_QA (n=9)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0 | 0.0 |
| Recall@5 | 0.1111 | 0.1111 |
| Recall@10 | 0.1111 | 0.2222 |
| MRR | 0.0222 | 0.0401 |
| Zero-hit rate | 0.8889 | 0.7778 |

**TRACE_CHAIN (n=9)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1111 | 0.2222 |
| Recall@5 | 0.3333 | 0.2222 |
| Recall@10 | 0.3333 | 0.4444 |
| MRR | 0.1704 | 0.2472 |
| Zero-hit rate | 0.6667 | 0.5556 |

**CHANGE_PLAN (n=15)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1333 | 0.4667 |
| Recall@5 | 0.2667 | 0.5333 |
| Recall@10 | 0.3333 | 0.6 |
| MRR | 0.1763 | 0.5095 |
| Zero-hit rate | 0.6667 | 0.4 |

### By system_answerable

**full (n=30)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1 | 0.2667 |
| Recall@5 | 0.2333 | 0.3333 |
| Recall@10 | 0.2667 | 0.4333 |
| MRR | 0.1393 | 0.3043 |
| Zero-hit rate | 0.7333 | 0.5667 |

**insufficient (n=3)**

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0 | 0.3333 |
| Recall@5 | 0.3333 | 0.3333 |
| Recall@10 | 0.3333 | 0.6667 |
| MRR | 0.0667 | 0.3667 |
| Zero-hit rate | 0.6667 | 0.3333 |

Note: The "insufficient" group here contains only source_answerable=true records whose
system_answerable is "insufficient" (meaning the system lacks some indexed data needed
for a full answer, but the source code does contain the answer).

## Key Observations

1. **Zero-hit rates are high across both baselines.** B0 has a 72.7% zero-hit rate and
   B1 has a 54.5% zero-hit rate on the main set. This means for the majority of queries,
   neither baseline retrieves any gold file in its top-10 results.

2. **Chinese queries dominate the zero-hit problem.** Chinese queries (n=21) have zero-hit
   rates of 81.0% (B0) and 66.7% (B1), compared to English (n=12) at 58.3% (B0) and
   33.3% (B1). This is expected because the token extraction step (split on whitespace/
   punctuation, minimum 3 characters) produces long compound Chinese tokens that do not
   match identifiers in source code. Chinese text lacks inter-word spaces, so entire
   phrases become single tokens.

3. **CODE_QA has the lowest recall for both baselines** (B0 R@10=0.11, B1 R@10=0.22,
   n=9). CODE_QA questions tend to ask about specific API endpoints or implementations
   whose identifiers may not appear literally in the question text.

4. **CHANGE_PLAN has the highest recall** for both baselines (B0 R@10=0.33, B1 R@10=0.60,
   n=15). Change-plan questions often mention specific feature names or module names that
   overlap with code identifiers.

5. **The "easy" difficulty group has zero recall for B0** (n=8). This is counterintuitive
   but likely reflects that "easy" questions tend to be in Chinese (these are
   human-perceived difficulty ratings) and suffer from the tokenization issue.

6. **B1 (keyword search) reports higher numbers than B0 (ripgrep) across nearly all
   metrics.** This is a factual observation, not a quality claim. B1 searches against
   a pre-indexed entity database (2,199 entities from scanning the repo), while B0
   searches raw file text. The two approaches have fundamentally different search
   targets and tokenization behavior.

## Limitations and Caveats

- **Small sample size.** The pilot dataset has only 42 records total, with 33
  source_answerable=true records contributing to the main metrics. Group-level
  breakdowns have very small n values (3 to 21), making point estimates unstable.
  Confidence intervals would be wide.

- **Token extraction bias.** Both baselines use the same token extraction logic
  (split on non-alphanumeric, min length 3). This systematically disadvantages
  Chinese-language queries. A Chinese word segmenter would likely improve both
  baselines for Chinese queries, but is not implemented.

- **File-level matching only.** These metrics measure whether any gold file appears
  in the top-k results. They do not measure line-level precision, entity-level
  recall, or whether the retrieved file contains the relevant code at the correct
  location.

- **No query rewriting.** Neither baseline applies Chinese-to-English translation
  or LLM-based query rewriting, which the full ResearchCode-Agent system uses.
  These baselines represent the lower bound of retrieval capability.

- **B0 searches raw text; B1 searches indexed entities.** The two baselines operate
  on different search corpora. B0 searches all text in source files (including
  comments, strings, etc.), while B1 searches only indexed code entity names and
  qualified names. Differences in metrics reflect this corpus difference, not
  just algorithmic quality.

- **The 7 excluded source_answerable=false records** have no must_recall gold
  entities. They represent questions that cannot be answered from the source code
  at all (e.g., asking about features that do not exist). Both baselines correctly
  return no relevant hits for the 2 diagnostic records that do have gold files.

## Configuration

- Dataset path: `evaluation/datasets/pilot.jsonl`
- Repository: `evaluation/workspaces/ruoyi-vue`
- B0 script: `evaluation/runners/baseline_rg.py`
- B1 script: `evaluation/runners/baseline_keyword.py`
- Top-k: 10
- B1 scan: 2,199 entities indexed from the repository
- Metrics script: `evaluation/scripts/compute_canonical_metrics.py`
- Full metrics JSON: `evaluation/results/metrics/canonical_baseline_metrics.json`
