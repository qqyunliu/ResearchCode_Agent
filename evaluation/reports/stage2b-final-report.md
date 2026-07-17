# Stage 2B Evaluation Report

## Scope and identity

- Dataset records: 36
- Dataset SHA-256: `86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c`
- Repository commit: `41720e624c5a668c7d3777835e4c87095a7a1dfd`
- Repositories: ruoyi-vue

## Environment

| Item | Recorded value |
|---|---|
| Models observed | mimo-v2.5 |
| Python | 3.11.15 |
| Qdrant mode | local |
| Retrieval top-k | 10 |

## B0-B5 summary

| Method | n | Main deterministic result |
|---|---:|---|
| B0 | 27 | File Recall@10=0.2222 |
| B1 | 27 | File Recall@10=0.3704 |
| B2 | 27 | File Recall@10=0.9815 |
| B3 | 27 | File Recall@10=0.9815 |
| B4 | 5 | Node P/R=0.1977/1.0000; edge P/R=0.2041/1.0000 |
| B5 | 36 | Routing accuracy=0.7500; evidence citation P/R=0.2521/0.4688; ID/path validity=1.0000/1.0000 |

## Retrieval degeneracy check

The hybrid comparison is not valid for attributing improvement: keyword branch returned zero effective ranking contribution; all compared Top-10 rankings are identical.

| Comparison | n | Identical Top-10 rate |
|---|---:|---:|
| B2 vs B3 | 36 | 1.0000 |
| A2 vs A3 vs A4 | 36 | 1.0000 |

## Graph depth ablation

| Variant | n | Node precision | Node recall | Edge precision | Edge recall |
|---|---:|---:|---:|---:|---:|
| A5 | 5 | 0.3200 | 0.9412 | 0.0000 | 0.0000 |
| A6 | 5 | 0.2152 | 1.0000 | 0.2381 | 1.0000 |
| B4 | 5 | 0.1977 | 1.0000 | 0.2041 | 1.0000 |

B4 (n=5) and A6 (n=5) have the same node and edge recall; there is no measured depth-2 gain on this Pilot.

## Ablations

- A1: `executable`
- A2: `executable`
- A3: `executable`
- A4: `executable`
- A5: `executable`
- A6: `executable`
- A7: `not_executable`: Canonical Pilot has no multi-turn cases; memory cannot be ablated fairly.
- A8: `executable`
- A9: `not_executable`: Product services expose no fair validate-without-repair switch.

## Per-variant latency

- B2: p50=2.5983s; p95=12.8425s
- B3: p50=2.3761s; p95=12.6456s
- B4: p50=2.3922s; p95=12.6599s
- A1: p50=0.0902s; p95=0.2236s
- A2: p50=2.3758s; p95=12.6448s
- A3: p50=2.3738s; p95=12.6438s
- A4: p50=2.3741s; p95=12.6450s
- A5: p50=2.3773s; p95=12.6475s
- A6: p50=2.3848s; p95=12.6534s
- B5: p50=18.7040s; p95=41.3794s
- A8: p50=20.2668s; p95=34.2253s

## Stability, refusal, and repair

| Measure | Value |
|---|---:|
| Stability questions | 8 |
| Exact answer-hash agreement | 0.0000 |
| reference Jaccard | 1.0000 |
| Graph-node Jaccard | 1.0000 |

semantic similarity was not evaluated; hash disagreement does not by itself prove semantic disagreement.

| Refusal/uncertainty population | n | Rate |
|---|---:|---:|
| Source-unanswerable (refusal detection) | 8 | 0.3750 |
| Source-answerable overall (over-refusal) | 28 | 0.0714 |
| Source-answerable, system full (over-refusal) | 22 | 0.0000 |
| Source-answerable partial/insufficient (over-refusal) | 6 | 0.3333 |
| Uncertainty disclosure expected | 17 | 0.4706 |

| Repair population | n | Attempted | Succeeded | Failed |
|---|---:|---:|---:|---:|
| B5 run 0 | 36 | 1 | 1 | 0 |
| B5 all scheduled runs | 52 | 3 | 2 | 1 |

## Cost evidence

- Provider attempts recorded: 91
- Total tokens recorded: 358576
- Monetary cost: `unknown` - Provider pricing was not pinned in evaluation metadata.

## Methodology boundary

An LLM judge was not used. Semantic answer correctness, required-claim coverage, and hallucination rate were not measured. ID/path validity only checks whether cited identifiers and paths are structurally valid; it is shown next to evidence precision/recall and must not be read as factual correctness.
A source-answerable partial/insufficient case should provide a qualified partial answer plus uncertainty; it is not an expected-refusal case.

## Limitations

- single development repository
- static analysis is best-effort and may miss runtime or dynamic behavior
- semantic answer correctness is not scored without a separately governed judge protocol
- This Pilot is based on a single development repository and does not establish cross-repository generalization.
- Temperature-zero model calls reduce but do not eliminate nondeterminism.
