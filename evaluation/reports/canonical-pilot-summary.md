# SUPERSEDED -- 42-record contaminated dataset

**Status:** This report has been SUPERSEDED by the Stage 2A.2 split.
**Reason:** Reflects the 42-record canonical dataset that mixed 36 synthetic
questions with 6 historical change cases (data leakage).
**Current valid report:** `evaluation/reports/stage2a2-final-report.md` (36 records)
**Current valid metrics:** `evaluation/results/metrics/pilot_current_summary.md`

---

# Canonical Pilot Dataset Summary

> **SUPERSESSION NOTICE**: This summary reflects the Stage 2A.1 canonical dataset
> of 42 records, which includes 6 historical change cases (HC-001 through HC-006)
> mixed with 36 synthetic questions. A pending Stage 2A.2 split will separate
> these into two tracks:
> - **36 synthetic questions** (CODE_QA: 12, TRACE_CHAIN: 12, CHANGE_PLAN: 12)
> - **6 historical change cases** (all CHANGE_PLAN, from real RuoYi-Vue commits)
>
> **This summary will be superseded by the Stage 2A.2 report** once the split
> is complete and metrics are recomputed on the separated tracks.

Generated: 2026-07-15T07:58:03+00:00
Dataset version: 1.2
Repository: ruoyi-vue
Commit: 41720e624c5a668c7d3777835e4c87095a7a1dfd

## Counts

| Metric | Count |
|--------|-------|
| Total curated questions | 42 |
| Total annotated questions | 42 |
| Total reviewed questions | 42 |
| Accepted | 42 |
| Needs review | 0 |
| Rejected (excluded) | 0 |
| **Final canonical records** | **42** |

Note: The 42 records comprise 36 synthetic questions and 6 historical change
cases (HC-001 through HC-006). The historical cases are pending separation into
a dedicated evaluation track as part of Stage 2A.2. After the split, the
synthetic-only canonical dataset will contain 36 records.

## Gold Status Distribution

| Gold Status | Count |
|-------------|-------|
| machine_verified | 42 |
| machine_proposed | 0 |

## Task Type Distribution

| Task Type | Count |
|-----------|-------|
| CODE_QA | 12 |
| TRACE_CHAIN | 12 |
| CHANGE_PLAN | 18 (12 synthetic + 6 historical) |

## Language Distribution

| Language | Count |
|----------|-------|
| zh | 24 |
| en | 18 |

## Difficulty Distribution

| Difficulty | Count |
|------------|-------|
| easy | 8 |
| medium | 22 |
| hard | 12 |

## Source Answerable Distribution

| source_answerable | Count |
|-------------------|-------|
| true | 33 |
| false | 9 |

## System Answerable Distribution

| system_answerable | Count |
|-------------------|-------|
| full | 30 |
| partial | 0 |
| insufficient | 12 |

## Historical Change Cases

Included: 6 historical change cases from real commits.

| Case ID | Commit Message | Change Type |
|---------|---------------|-------------|
| 角色权限变更后刷新所有持有该角色的在线用户权限 | 2 files changed, 41 insertions(+), 11 deletions(-) | historical_change |
| 修复脱敏不生效问题(IIPBZR) | 3 files changed, 29 insertions(+), 19 deletions(-) | historical_change |
| 用户列表新增抽屉效果详细信息 | 5 files changed, 242 insertions(+), 3 deletions(-) | historical_change |
| 菜单管理支持批量保存排序 | 7 files changed, 126 insertions(+), 3 deletions(-) | historical_change |
| 优化定时任务详情页展示&补充执行时间字段 | 10 files changed, 298 insertions(+), 160 deletions(-) | historical_change |
| 首页新增通知公告消息提醒 | 13 files changed, 677 insertions(+), 10 deletions(-) | historical_change |

## Coverage Gaps

- CALLS_METHOD relations are not stored in the static index, so TRACE_CHAIN questions involving controller-to-service chains are rated "insufficient"
- Dynamic URL frontend requests cannot be traced via REQUESTS_API in the index
- Some hypothetical CHANGE_PLAN questions reference service-layer files not fully indexed

## Notes

- No `gold_status` is set to `human_verified` (reserved for human review)
- All file paths verified against repository at commit 41720e624c5a668c7d3777835e4c87095a7a1dfd
- All stable_entity_keys computed using stable_entity_key.py algorithm
