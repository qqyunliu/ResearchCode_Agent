# Hybrid Fusion Weight Selection

## Decision

The production hybrid-search weights are changed from **0.70 vector / 0.30
keyword** to **0.75 vector / 0.25 keyword**.

This is a bounded calibration result, not a claim that 0.75/0.25 is universally
optimal. On the frozen RuoYi-Vue development Pilot, it improves first-result
ranking while preserving Recall@5 and Recall@10. The eligible set contains 27
source-answerable retrieval cases from one repository.

## Frozen experiment

- Dataset SHA-256: `86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c`
- Repository commit: `41720e624c5a668c7d3777835e4c87095a7a1dfd`
- SQLite SHA-256: `cffd46aa7a2d495877dea84ed6eb613d0a78ce9f9cd19808cb6d720fbf9e1049`
- Snapshot SHA-256: `2eb5eb8148e088f08159fc4605466ba0473145f2ae6217b6d89bac697bf61504`
- Run ID: `fusion-weight-sweep-v1`
- Schedule: 36 questions x 9 variants = 324 records
- Metric population: 27 source-answerable retrieval cases
- Fusion: independently max-normalize the vector and keyword branches, then
  compute a weighted sum and deduplicate by entity.

The sweep used B2 vector-only plus vector weights from 0.60 through 0.95 in
0.05 increments. Query text, candidate-generation configuration, snapshot,
dataset, and metric code were held fixed; only the two complementary fusion
weights changed.

## Results

| Variant | Vector / keyword | Recall@1 | Recall@5 | Recall@10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | vector only | 0.5278 | 0.9352 | 0.9815 | 0.8210 |
| W60 | 0.60 / 0.40 | 0.5648 | 0.9722 | 0.9815 | 0.8488 |
| W65 | 0.65 / 0.35 | 0.5648 | 0.9722 | 0.9815 | 0.8488 |
| W70 (old) | 0.70 / 0.30 | 0.5648 | 0.9722 | 0.9815 | 0.8488 |
| **W75 (selected)** | **0.75 / 0.25** | **0.6019** | **0.9722** | **0.9815** | **0.8673** |
| W80 | 0.80 / 0.20 | 0.6019 | 0.9722 | 0.9815 | 0.8673 |
| W85 | 0.85 / 0.15 | 0.6019 | 0.9722 | 0.9815 | 0.8673 |
| W90 | 0.90 / 0.10 | 0.6019 | 0.9722 | 0.9815 | 0.8673 |
| W95 | 0.95 / 0.05 | 0.4537 | 0.9722 | 0.9815 | 0.8025 |

Relative to the old W70 setting, W75 changes:

- Recall@1: `0.5648 -> 0.6019` (`+0.0371`, one additional case at rank 1)
- Recall@5: `0.9722 -> 0.9722` (no regression)
- Recall@10: `0.9815 -> 0.9815` (no regression)
- MRR: `0.8488 -> 0.8673` (`+0.0185`)

The improvement is localized to `ruoyi-code-qa-0004`, whose correct backend
implementation moves from rank 2 to rank 1. At W70, a frontend API wrapper is
ranked just above the backend controller. Slightly reducing the lexical weight
allows the semantically closer controller implementation to lead. No eligible
case loses Recall@5, including the language and task-type slices.

## Selection rule

The rule was written before reading the sweep outcome. A candidate had to:

1. preserve the frozen Recall@10 floor of 0.9815;
2. preserve the old W70 Recall@5 floor of 0.9722;
3. strictly improve Recall@5 or MRR over W70; and
4. avoid a Recall@5 regression in every language and task-type group.

Qualified candidates were ordered by Recall@5, then MRR, then Recall@1, then
smallest distance from the existing 0.70 vector weight. W75, W80, W85, and W90
form an identical metric plateau. W75 is selected because it is the smallest
production change, not because the experiment can distinguish it from the
other points on that plateau.

The endpoint behavior is also informative: W95 loses both Recall@1 and MRR.
The keyword branch therefore remains useful, but 0.30 gives it enough influence
to misorder one implementation question in this Pilot, while 0.25 retains its
coverage contribution without that observed misordering.

## Robustness and limitations

A paired 10,000-resample bootstrap (seed `20260717`) gives the W75-minus-W70
MRR interval `[0.0000, 0.0556]`; the Recall@5 delta is always zero. Leave-one-case-
out selection chooses W75 for 26 of 27 omissions and produces no winner when
the one improved case is removed.

Consequently, the result is not statistically significant evidence of a
universal optimum. It is a reproducible engineering calibration on a frozen
single-repository development Pilot. A held-out, multi-repository evaluation
is required before claiming cross-project generalization.

The real rewrite provider was unstable during two earlier attempts. The final
sweep therefore replayed the 36-query rewrite cache from the previously
approved, independently audited run. It made 36 successful embedding calls and
zero new rewrite calls. The metrics gate validated the empty rewrite ledger; an
independent artifact audit verified that the 36-entry cache was byte-identical
to the approved reference cache and that every raw effective query matched it.
This keeps effective queries fixed across all weights, which is desirable for
isolating the weight variable, but it must not be described as a fresh
rewrite-model run.

## Interview-safe explanation

> We originally used 0.7/0.3 as a heuristic. I froze the repository snapshot,
> queries, rewrite outputs, candidates, and evaluation set, then swept vector
> weights from 0.60 to 0.95. I predeclared that a replacement could not reduce
> Recall@5, Recall@10, or any language/task Recall@5 slice. The 0.75-to-0.90
> range tied, improving MRR from 0.8488 to 0.8673 and Recall@1 from 0.5648 to
> 0.6019 while keeping Recall@5 at 0.9722 and Recall@10 at 0.9815. I chose 0.75
> as the closest point to the old setting. The gain came from moving one correct
> backend implementation from rank 2 to rank 1, so I treat it as a single-repo
> Pilot calibration, not a universal optimum.

Canonical artifacts:

- `evaluation/results/raw/fusion_weight_sweep_retrieval.jsonl`
- `evaluation/results/raw/fusion_weight_sweep_retrieval.metadata.json`
- `evaluation/results/metrics/fusion_weight_sweep_metrics.json`
