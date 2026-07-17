# Pilot-Current Baseline Retrieval Metrics

## Dataset

- **Dataset**: `evaluation/datasets/pilot-current.jsonl`
- **SHA-256**: `eabda374f8a1f717924537b03dc37f0b47fa25acd71498da45360a8f98b4c78e`
- **Total records**: 36
- **Eligible records** (machine_verified + accepted + executable + retrieval layer): 36
- **Records with gold files** (must_recall entities with file_path):
  - source_answerable=true: 27
  - source_answerable=false (diagnostic): 2
- **Records without gold files** (skipped from recall): 7

## Overall Metrics (source_answerable=true)

| Metric | B0 (ripgrep, n=27) | B1 (keyword, n=27) |
|---|---|---|
| Recall@1 | 0.0741 | 0.1852 |
| Recall@5 | 0.2222 | 0.2593 |
| Recall@10 | 0.2593 | 0.4074 |
| Mrr | 0.1177 | 0.2307 |
| Zero Hit Rate | 0.7407 | 0.5926 |

## Diagnostic Metrics (source_answerable=false)

| Metric | B0 (ripgrep, n=2) | B1 (keyword, n=2) |
|---|---|---|
| Recall@1 | 0.0000 | 0.0000 |
| Recall@5 | 0.0000 | 0.0000 |
| Recall@10 | 0.0000 | 0.0000 |
| Mrr | 0.0000 | 0.0000 |
| Zero Hit Rate | 1.0000 | 1.0000 |

## Grouped Metrics (source_answerable=true only)

### By Language

**en** (B0 n=12, B1 n=12)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0000 | 0.2500 |
| Recall@5 | 0.3333 | 0.4167 |
| Recall@10 | 0.4167 | 0.6667 |
| Mrr | 0.0981 | 0.3441 |
| Zero Hit Rate | 0.5833 | 0.3333 |

**zh** (B0 n=15, B1 n=15)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1333 | 0.1333 |
| Recall@5 | 0.1333 | 0.1333 |
| Recall@10 | 0.1333 | 0.2000 |
| Mrr | 0.1333 | 0.1400 |
| Zero Hit Rate | 0.8667 | 0.8000 |

### By Difficulty

**easy** (B0 n=8, B1 n=8)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0000 | 0.0000 |
| Recall@5 | 0.0000 | 0.2500 |
| Recall@10 | 0.0000 | 0.2500 |
| Mrr | 0.0000 | 0.0938 |
| Zero Hit Rate | 1.0000 | 0.7500 |

**hard** (B0 n=7, B1 n=7)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0000 | 0.0000 |
| Recall@5 | 0.2857 | 0.0000 |
| Recall@10 | 0.2857 | 0.2857 |
| Mrr | 0.0762 | 0.0383 |
| Zero Hit Rate | 0.7143 | 0.7143 |

**medium** (B0 n=12, B1 n=12)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1667 | 0.4167 |
| Recall@5 | 0.3333 | 0.4167 |
| Recall@10 | 0.4167 | 0.5833 |
| Mrr | 0.2204 | 0.4343 |
| Zero Hit Rate | 0.5833 | 0.4167 |

### By Task Type

**CHANGE_PLAN** (B0 n=9, B1 n=9)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1111 | 0.3333 |
| Recall@5 | 0.2222 | 0.4444 |
| Recall@10 | 0.3333 | 0.5556 |
| Mrr | 0.1605 | 0.4048 |
| Zero Hit Rate | 0.6667 | 0.4444 |

**CODE_QA** (B0 n=9, B1 n=9)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.0000 | 0.0000 |
| Recall@5 | 0.1111 | 0.1111 |
| Recall@10 | 0.1111 | 0.2222 |
| Mrr | 0.0222 | 0.0401 |
| Zero Hit Rate | 0.8889 | 0.7778 |

**TRACE_CHAIN** (B0 n=9, B1 n=9)

| Metric | B0 | B1 |
|---|---|---|
| Recall@1 | 0.1111 | 0.2222 |
| Recall@5 | 0.3333 | 0.2222 |
| Recall@10 | 0.3333 | 0.4444 |
| Mrr | 0.1704 | 0.2472 |
| Zero Hit Rate | 0.6667 | 0.5556 |

## Comparison with Old Contaminated Baseline (pilot.jsonl)

The old `pilot.jsonl` dataset (42 records) was found to contain data contamination
from proposed annotations. This `pilot-current.jsonl` (36 records) is the clean
version with only verified gold data.

Key differences:
- Record count: 36 (current) vs 42 (old)
- All 36 current records have execution_status='executable'
- Language split: 18 zh / 18 en (balanced), vs the old dataset's imbalance
- Task types: 12 CODE_QA / 12 TRACE_CHAIN / 12 CHANGE_PLAN (balanced)

## Configuration

- B1 scan: 2199 entities indexed from the repository
- Top-k: 10
- Metrics script: `evaluation/scripts/compute_pilot_current_metrics.py`
- Full metrics JSON: `evaluation/results/metrics/pilot_current_metrics.json`
