# Stage 2A.1 Baseline Results -- SUPERSEDED

Archived: 2026-07-15T16:19:17+08:00

## Reason for archiving

These baseline metrics were computed on the canonical pilot dataset of **42
records** that included **6 historical change cases** (HC-001 through HC-006,
sourced from real RuoYi-Vue commits) mixed with **36 synthetic questions**.

The inclusion of historical change cases in the same evaluation track as
synthetic questions constitutes **historical data leakage**: the baseline
scripts and metrics were designed and tuned on a dataset that was not purely
synthetic. This means the reported metrics do not accurately reflect the
system's performance on synthetic questions alone.

## Files in this archive

| File | Description |
|------|-------------|
| `canonical_b0_rg.jsonl` | B0 (ripgrep) baseline predictions for all 42 records |
| `canonical_b0_rg.jsonl.SUPERSEDED.txt` | Supersession marker for B0 predictions |
| `canonical_b1_keyword.jsonl` | B1 (keyword search) baseline predictions for all 42 records |
| `canonical_b1_keyword.jsonl.SUPERSEDED.txt` | Supersession marker for B1 predictions |
| `canonical_baseline_metrics.json` | Aggregated metrics JSON (marked with `_SUPERSEDED` key) |
| `canonical_baseline_summary.md` | Human-readable metrics summary (marked with SUPERSEDED banner) |

## What happens next

The Stage 2A.2 process will:

1. Split the 42-record canonical dataset into:
   - 36 synthetic questions (CODE_QA: 12, TRACE_CHAIN: 12, CHANGE_PLAN: 12)
   - 6 historical change cases (all CHANGE_PLAN, in a separate evaluation track)
2. Re-run B0 and B1 baselines on the 36-record synthetic-only dataset
3. Compute corrected metrics and produce a new Stage 2A.2 report
4. The historical change cases will be evaluated separately in a dedicated
   historical-change evaluation track

## Do not use these files for decision-making

These archived files are retained for audit trail and provenance tracking only.
Do not cite or compare against these metrics in future evaluation reports.
