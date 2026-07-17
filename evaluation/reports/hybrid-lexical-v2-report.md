# Hybrid Lexical v2 Retrieval Report

## Scope

This post-fix run evaluates the repaired code-aware lexical branch on the
36-question RuoYi-Vue Pilot at commit
`41720e624c5a668c7d3777835e4c87095a7a1dfd`. Retrieval metrics use the 27
`source_answerable=true` cases with indexed `must_recall` gold entities.
File Recall@K is the mean fraction of required gold files present in the first
K distinct retrieved files; it is not the weaker "at least one hit" measure.

This historical pre-calibration production comparison is B2 vector-only versus
B3 hybrid with the then-current vector/keyword weights of 0.7/0.3. Weight
variants in this run are diagnostic ablations, not the subsequently selected
production default.

## Result

| Variant | Description | Recall@1 | Recall@5 | Recall@10 | MRR | Zero-hit |
|---|---|---:|---:|---:|---:|---:|
| B2 | vector-only, rewrite on | 0.5278 | 0.9352 | 0.9815 | 0.8210 | 0.0000 |
| B3 | hybrid 0.7/0.3, rewrite on | 0.5648 | 0.9722 | 0.9815 | 0.8488 | 0.0000 |
| A1 | hybrid 0.7/0.3, rewrite off | 0.6389 | 0.9722 | 0.9815 | 0.8951 | 0.0000 |
| A2 | hybrid 0.5/0.5, rewrite on | 0.5093 | 0.9722 | 0.9815 | 0.8025 | 0.0000 |
| A3 | hybrid 0.3/0.7, rewrite on | 0.4907 | 0.7870 | 0.7963 | 0.7173 | 0.1481 |
| A4 | RRF, rewrite on | 0.5463 | 0.9352 | 0.9815 | 0.8241 | 0.0000 |

B3 improves over B2 by 0.0370 Recall@5 and 0.0278 MRR while preserving
Recall@10. It also improves Recall@1 by 0.0370. The predeclared acceptance gate
therefore passes.

The Recall@5 gain is traceable to `ruoyi-change-plan-0026`: its first correct
file moves from rank 6 under B2 to rank 1 under B3. Across cases whose first
correct rank changed, five improve and four regress; the aggregate MRR remains
positive. This is an aggregate improvement, not a claim that hybrid improves
every query.

## Lexical contribution

For B3 across all 36 questions:

- mean vector candidates: 20.0000;
- mean keyword candidates: 20.0000;
- mean overlap: 5.2778;
- mean keyword-only candidates: 14.7222;
- Top-10 changed from vector-only: 33/36 questions;
- B2/B3 identical Top-10 rate: 0.0833.

The keyword branch therefore contributes materially different candidates; the
result is not the previous hybrid-degeneration case where B2 and B3 were
identical.

## Integrity and reproducibility

- dataset SHA-256:
  `86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c`;
- lexical implementation: `code_aware_multiterm_v2`;
- raw records: 216/216, all `status=ok`;
- embedding calls: 89 successes, 0 failures, 0 pending/unconfirmed;
- rewrite calls: 18 successes, 0 failures, 0 pending/unconfirmed;
- provider ledger: 0 pending, 0 unconfirmed, 0 orphan for both providers;
- vector build: 2,199 entities/points in an isolated Qdrant path;
- raw SHA-256:
  `48f7da1b82c761490da798d55a4109f01eb3fb200298780b0313f8442ea1bf1d`;
- metadata SHA-256:
  `03c446801902854efeeac7eab8920a5f32d810eb1dbc45ca23cee3845f9e9232`;
- metrics SHA-256:
  `1896a86b27b42fe769748ea37b4f7d50c2ced0d009b5ece65f8599964b0b7244`.

## Claim boundary

Safe claim: on this fixed single-repository Pilot, the repaired code-aware
lexical branch made fixed-weight hybrid retrieval outperform vector-only on
Recall@5 and MRR without reducing Recall@10.

Do not claim universal superiority, cross-repository generalization, or that
0.7/0.3 is globally optimal. A1's stronger MRR also shows that query rewriting
interacts with lexical retrieval and deserves a separate experiment. A3 shows
that overweighting the lexical branch can materially degrade retrieval.
