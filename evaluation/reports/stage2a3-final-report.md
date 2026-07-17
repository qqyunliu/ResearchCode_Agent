# ResearchCode-Agent Evaluation Report

**Dataset SHA-256**: `86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c`

**Generated**: 2026-07-15T11:45:50.051033+00:00

---

# Section A: Dataset Summary

## Dataset Identity

- **Dataset path**: `evaluation/datasets/pilot-current.jsonl`
- **SHA-256**: `86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c`
- **Repository commit**: `41720e624c5a668c7d3777835e4c87095a7a1dfd`

## Record Counts

- **Total records**: 36
- **Eligible records**: 36
- **source_answerable=true**: 28
- **source_answerable=false**: 8
- **No gold files**: 0
- **Skipped: no indexable gold**: 1

## Cross-Distribution Tables

### Task Type x Language

| task_type \ language | en | zh | total |
|---|---|---|---|
| CHANGE_PLAN | 6 | 6 | 12 |
| CODE_QA | 6 | 6 | 12 |
| TRACE_CHAIN | 6 | 6 | 12 |
| **total** | 18 | 18 | 36 |

### Task Type x Difficulty

| task_type \ difficulty | easy | hard | medium | total |
|---|---|---|---|---|
| CHANGE_PLAN | 2 | 5 | 5 | 12 |
| CODE_QA | 4 | 3 | 5 | 12 |
| TRACE_CHAIN | 2 | 4 | 6 | 12 |
| **total** | 8 | 12 | 16 | 36 |

### Task Type x system_answerable

| task_type \ system_answerable | full | insufficient | partial | total |
|---|---|---|---|---|
| CHANGE_PLAN | 9 | 3 | 0 | 12 |
| CODE_QA | 8 | 4 | 0 | 12 |
| TRACE_CHAIN | 5 | 4 | 3 | 12 |
| **total** | 22 | 11 | 3 | 36 |

# Section B: Baseline Results

## Overall Metrics

| Metric | B0 (b0_rgrep, n=27) | B1 (b1_keyword, n=27) |
|---|---|---|
| recall@1 | 0.0741 | 0.1852 |
| recall@5 | 0.2222 | 0.2593 |
| recall@10 | 0.2222 | 0.4074 |
| mrr | 0.1105 | 0.2307 |
| zero_hit_rate | 0.7778 | 0.5926 |

## Diagnostic: source_answerable=false

| Metric | B0 (n=1) | B1 (n=1) |
|---|---|---|
| recall@1 | 0.0000 | 0.0000 |
| recall@5 | 0.0000 | 0.0000 |
| recall@10 | 0.0000 | 0.0000 |
| mrr | 0.0000 | 0.0000 |
| zero_hit_rate | 1.0000 | 1.0000 |

## Grouped by language

### B0 (b0_rgrep)

| language | n | recall@1 | recall@5 | recall@10 | mrr | zero_hit_rate |
|---|---|---|---|---|---|---|
| en | 13 | 0.0000 | 0.3077 | 0.3077 | 0.0756 | 0.6923 |
| zh | 14 | 0.1429 | 0.1429 | 0.1429 | 0.1429 | 0.8571 |

### B1 (b1_keyword)

| language | n | recall@1 | recall@5 | recall@10 | mrr | zero_hit_rate |
|---|---|---|---|---|---|---|
| en | 13 | 0.2308 | 0.3846 | 0.6154 | 0.3176 | 0.3846 |
| zh | 14 | 0.1429 | 0.1429 | 0.2143 | 0.1500 | 0.7857 |

## Grouped by difficulty

### B0 (b0_rgrep)

| difficulty | n | recall@1 | recall@5 | recall@10 | mrr | zero_hit_rate |
|---|---|---|---|---|---|---|
| easy | 8 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| hard | 8 | 0.0000 | 0.2500 | 0.2500 | 0.0667 | 0.7500 |
| medium | 11 | 0.1818 | 0.3636 | 0.3636 | 0.2227 | 0.6364 |

### B1 (b1_keyword)

| difficulty | n | recall@1 | recall@5 | recall@10 | mrr | zero_hit_rate |
|---|---|---|---|---|---|---|
| easy | 8 | 0.0000 | 0.2500 | 0.2500 | 0.0938 | 0.7500 |
| hard | 8 | 0.0000 | 0.0000 | 0.2500 | 0.0335 | 0.7500 |
| medium | 11 | 0.4545 | 0.4545 | 0.6364 | 0.4737 | 0.3636 |

## Grouped by task_type

### B0 (b0_rgrep)

| task_type | n | recall@1 | recall@5 | recall@10 | mrr | zero_hit_rate |
|---|---|---|---|---|---|---|
| CHANGE_PLAN | 9 | 0.1111 | 0.2222 | 0.2222 | 0.1389 | 0.7778 |
| CODE_QA | 8 | 0.0000 | 0.1250 | 0.1250 | 0.0250 | 0.8750 |
| TRACE_CHAIN | 10 | 0.1000 | 0.3000 | 0.3000 | 0.1533 | 0.7000 |

### B1 (b1_keyword)

| task_type | n | recall@1 | recall@5 | recall@10 | mrr | zero_hit_rate |
|---|---|---|---|---|---|---|
| CHANGE_PLAN | 9 | 0.3333 | 0.4444 | 0.5556 | 0.4048 | 0.4444 |
| CODE_QA | 8 | 0.0000 | 0.1250 | 0.2500 | 0.0451 | 0.7500 |
| TRACE_CHAIN | 10 | 0.2000 | 0.2000 | 0.4000 | 0.2225 | 0.6000 |

# Section C: Consistency Checks

## Record Count Reconciliation

```
dataset_records (36) = source_answerable_true (28) + source_answerable_false (8) + no_gold_files (0) = 36
  => PASS
```

## Retrieval Layer Scope

```
retrieval_layer_records (36) <= dataset_records (36)
  => PASS
```

## Scored Records Scope

```
b0_rgrep.overall.n (27) <= retrieval_layer_records (36)
  => PASS
b1_keyword.overall.n (27) <= retrieval_layer_records (36)
  => PASS
```

# Section D: Caveats

1. **Single-repo pilot.** All metrics are computed on a single repository (ruoyi-vue). Results may not generalize to other codebases, languages, or project structures.

2. **Text-search baselines only.** B0 (ripgrep) and B1 (SQLite keyword search) are text-matching baselines. They do not use vector retrieval, query rewriting, or LLM-assisted search. These results represent a lower bound on retrieval capability.

3. **File-level matching.** Metrics measure whether any gold file appears in the top-k results. They do not measure line-level precision, entity-level recall, or whether the retrieved file contains the relevant code at the correct location.

4. **Small sample size.** The pilot dataset has a limited number of records. Group-level breakdowns have very small n values, making point estimates unstable.

5. **Token extraction bias.** Both baselines use whitespace/punctuation-based token extraction, which systematically disadvantages Chinese-language queries due to the lack of inter-word spaces in Chinese text.

6. **Offline evaluation.** These are offline metrics computed against a fixed gold set. They do not reflect interactive Agent performance where users can refine queries.
