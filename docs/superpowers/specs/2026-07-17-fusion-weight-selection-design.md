# Fusion Weight Selection Design

## 1. Goal

Select a vector/keyword fusion ratio that improves on the current 0.7/0.3
setting with reproducible evidence and an interview-safe explanation. The
experiment must distinguish a development-set choice from a universally optimal
production constant.

## 2. Alternatives considered

1. **Pick the maximum score on all 27 cases.** Fast, but too easy to challenge
   as test-set tuning.
2. **Fixed coarse grid plus robustness analysis.** Evaluate a predeclared grid,
   retain the current gold contract, and require aggregate and subgroup
   stability. This is the selected approach.
3. **Learn a query-dependent weight.** Potentially stronger, but the Pilot is
   too small to train and validate a gating model without obvious overfitting.

## 3. Frozen experiment

- Repository: RuoYi-Vue commit
  `41720e624c5a668c7d3777835e4c87095a7a1dfd`.
- Dataset SHA-256:
  `86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c`.
- Eligible retrieval cases: the existing 27 `source_answerable=true` cases
  with indexed `must_recall` gold.
- Query rewriting, embedding model, candidate limit, score normalization,
  lexical implementation, Qdrant snapshot, and Top-K remain unchanged.
- The previously approved
  `hybrid_lexical_v2_fresh_retrieval.metadata.json` is a required reference
  artifact. The sweep must match its provider/model/dimension/endpoint, chunk
  size, Top-K, candidate limit, and lexical implementation fields. The sweep
  config fingerprint is recomputed rather than trusted as a string.
- Candidate vector weights are fixed before running:
  `0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95`; keyword weight is
  `1 - vector_weight`.
- B2 vector-only is retained as the no-keyword reference.

The grid is intentionally coarse. A fine-grained search could find a prettier
number but would increase development-set overfitting without adding an
engineering insight.

## 4. Fair execution

The evaluation runner exposes weight-sweep variants only when explicitly
selected; the frozen default Stage 2B schedule remains unchanged. All sweep
variants use the same effective query and the same source retrieval
configuration. Query rewrites and embeddings remain cached by effective query,
so adding weights does not multiply provider calls.

Each raw record carries the exact vector/keyword weights, the lexical
implementation version, stable entity keys, and branch diagnostics. A new run
identity, output path, metadata path, ledger directory, and metrics path are
mandatory.

The metrics command replays the actual embedding and rewrite durable ledgers in
read-only mode and compares their counts with metadata. It rejects missing,
torn, duplicated, unfinished, or mismatched events. Output is written through a
same-directory temporary file, flushed, synced, and atomically replaced; output
may not alias any input artifact.

## 5. Metrics and selection rule

Report File Recall@1, Recall@5, Recall@10, MRR, zero-hit rate, task type,
language, and difficulty groups. Also report per-case first-correct rank changes
against 0.7/0.3.

The selected weight must satisfy all hard gates:

1. Recall@10 is not below 0.9815, the frozen vector-only and 0.7/0.3 result.
2. Recall@5 is not below 0.9722, the repaired 0.7/0.3 result.
3. It improves MRR over 0.8488 or improves Recall@5 beyond 0.9722.
4. No task-type or language group loses Recall@5 relative to 0.7/0.3.
5. All raw records are successful and all provider ledgers are closed.

Among eligible candidates, select lexicographically by:

1. highest Recall@5;
2. highest MRR;
3. highest Recall@1;
4. smallest absolute distance from 0.7, to avoid an unnecessary large change.

Before candidate selection, the current sweep's B2 Recall@10, W70 Recall@5, and
W70 MRR must also meet the frozen absolute values 0.9815, 0.9722, and 0.8488.
This prevents a degraded rerun from selecting a merely relative winner.

Robustness evidence includes deterministic bootstrap resampling frequencies of
eligible cases and leave-one-case-out winner frequency. These are resampling
frequencies, not posterior probabilities. They do not replace the hard gates;
they show whether the apparent winner depends on one question.

Leave-one-case-out recomputes the relative W70 comparison, subgroup gates, and
winner ordering on each 26-case subset, but does not reuse the 27-case absolute
numeric floors. Reusing those floors after changing the denominator would create
artificial `no_winner` outcomes rather than measure case sensitivity.

## 6. Production change boundary

The experiment first produces evaluation evidence only. The product default is
changed in a separate, test-first step after the winning ratio passes an
independent data audit. Product tests must lock the selected weights and preserve
fallback, normalization, deterministic ordering, and response schemas.

## 7. Claim boundary

Safe claim: a predeclared coarse sweep on the fixed development Pilot selected
a more effective vector-dominant ratio under Recall@5, Recall@10, MRR, and
subgroup constraints.

Unsafe claims: the ratio is universally optimal, generalizes across repositories,
or was selected on a held-out test set. Cross-repository validation remains the
next step required for a stronger claim.
