# Stage 2A.3 Post-Fix Resolution

## Scope

This is a deterministic resolution check of the findings recorded in
`post-fix-blind-audit.md`. It is not presented as another independent blind
review.

- Dataset: `evaluation/datasets/pilot-current.jsonl`
- Dataset version: `1.4`
- Dataset SHA-256: `86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c`
- Repository commit: `41720e624c5a668c7d3777835e4c87095a7a1dfd`
- Records: 36

## Finding Resolution

| Prior finding | Resolution | Verification |
|---|---|---|
| TRACE_CHAIN 0020 lacked `chain_complete` and contradicted `system_answerable=full` | Set `chain_complete=false` and `system_answerable=insufficient`; retained explicit uncertainty for the unindexed node | Schema and snapshot validators pass |
| TRACE_CHAIN 0023 lacked `chain_complete` | Set `chain_complete=false`; the empty graph gold now explicitly represents an incomplete chain | Schema and snapshot validators pass |
| TRACE_CHAIN 0015 used a placeholder key | Replaced it with a 64-character stable entity key and source-only evidence for the missing service method | Stable-key and snapshot rules pass |
| TRACE_CHAIN 0016 used a placeholder key | Replaced it with a 64-character stable entity key and source-only evidence for the missing service method | Stable-key and snapshot rules pass |
| Formal metrics referenced the pre-fix dataset | Reran B0/B1 and regenerated metrics and report against the current SHA | Metrics reconciliation passes |

## Current Validation Result

- Dataset Schema: 36 passed, 0 structural errors, 0 semantic errors.
- Snapshot consistency: 36 passed, 0 violations.
- `pilot.jsonl` is byte-identical to `pilot-current.jsonl`.
- All 36 records declare dataset version `1.4`.

The former Critical and Major findings are closed for the current dataset.
This does not turn source-only entities into indexed entities: those remain
deliberate system false-negative evidence and are excluded from index-level
retrieval gold.
