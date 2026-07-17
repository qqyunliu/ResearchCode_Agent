> **SUPERSEDED:** This audit describes dataset SHA
> `f7b8eed768ffc8d569dba8b14edffa28f77e6e73cd1810a0a3eead5db7ac5178`
> before its five findings were repaired. It is retained as audit history;
> current closure evidence is in `post-fix-resolution.md`.

# Post-Fix Blind Audit Report

## 1. Agent Identification

| Field | Value |
|---|---|
| Agent | audit_agent_F |
| Audit type | Post-fix blind audit (independent from all prior agents) |
| Date | 2026-07-15 |

## 2. Dataset Reference

| Field | Value |
|---|---|
| Dataset file | `pilot-current.jsonl` |
| SHA-256 | `f7b8eed768ffc8d569dba8b14edffa28f77e6e73cd1810a0a3eead5db7ac5178` |
| SHA-256 verified | YES |
| Total records | 36 |
| TRACE_CHAIN records | 12 (0013-0024) |
| CODE_QA records | 12 (0001-0012) |
| CHANGE_PLAN records | 12 (0025-0036) |
| Snapshot entities | 2,199 |
| Snapshot relations | 1,980 |

## 3. TRACE_CHAIN Audit Results (Records 0013-0024)

### 3.1 Per-Record Summary

| Record | Lang | chain_complete | system_answerable | Entities | Nodes | Edges | Missing Keys | Status |
|--------|------|---------------|-------------------|----------|-------|-------|-------------|--------|
| 0013 | zh | true | full | 3 | 3 | 2 | 0 | CLEAN |
| 0014 | en | true | full | 3 | 3 | 2 | 0 | CLEAN |
| 0015 | zh | false | insufficient | 1 | 2 | 1 | 1 | 1 Major + 1 Minor |
| 0016 | en | false | insufficient | 1 | 2 | 1 | 1 | 1 Major + 1 Minor |
| 0017 | zh | true | full | 3 | 3 | 2 | 0 | CLEAN |
| 0018 | en | false | partial | 2 | 2 | 1 | 1 | CLEAN |
| 0019 | zh | true | full | 3 | 3 | 2 | 0 | CLEAN |
| 0020 | en | **MISSING** | full | 1 | 1 | 0 | 0 | **2 CRITICAL + 1 Minor** |
| 0021 | zh | true | full | 5 | 5 | 2 | 0 | CLEAN |
| 0022 | en | false | partial | 6 | 6 | 4 | 2 | CLEAN |
| 0023 | zh | **MISSING** | insufficient | 0 | 0 | 0 | 0 | **1 CRITICAL** |
| 0024 | en | false | partial | 2 | 2 | 1 | 1 | CLEAN |

### 3.2 Entity Key Verification

All 35 gold_entities across 12 TRACE_CHAIN records were verified:

- **Key recomputation**: All 35 stored `stable_entity_key` values match the SHA-256 recomputation from `stable_entity_key.py`. Zero mismatches.
- **Snapshot presence**: All entities with `indexed_in_system=true` have their keys present in `code_entities.json`. Zero false claims.

### 3.3 Node Key Verification

All 36 gold_nodes across 12 TRACE_CHAIN records were verified:

- **34 nodes** have valid 64-character hex SHA-256 keys. All indexed nodes are present in the snapshot.
- **2 nodes** (records 0015 and 0016) use non-standard placeholder keys. See Major findings below.

### 3.4 Edge Verification

All 17 gold_edges across 12 TRACE_CHAIN records were verified:

- All source_key and target_key values reference valid gold_nodes.
- All indexed edges have matching `(source_key, target_key, relation_type)` triples in `code_relations.json`.
- No edge claimed as unindexed actually exists in the snapshot.
- Zero direction errors. Zero relation type mismatches.

### 3.5 Detailed Findings

#### CRITICAL -- Record 0020: Missing `chain_complete` field + system_answerable contradictions

The `chain_complete` field is **entirely absent** from the JSON record (not `false`, not `null` -- the key does not exist).

Contradictions found:

| Check | Expected | Actual |
|-------|----------|--------|
| `chain_complete` present | `true` (required field) | Field missing |
| `system_answerable=full` + `expected_uncertainties` | Empty uncertainties | 3 uncertainties listed |
| `system_answerable=full` + `source_answerable` | Consistent | `source_answerable=false` |

The record describes a trace for POST /logout, which is handled by Spring Security LogoutFilter rather than any controller. The annotation notes say "Unanswerable trace" -- this directly contradicts `system_answerable=full`.

**Required fix**: Set `chain_complete=false` and change `system_answerable` to `partial` or `insufficient` (the trace cannot be completed because no backend_api entity exists for /logout).

#### CRITICAL -- Record 0023: Missing `chain_complete` field

The `chain_complete` field is **entirely absent** from the JSON record.

This record describes a trace for POST /system/user/batchDelete, an endpoint that does not exist. With 0 gold entities, 0 gold nodes, and 0 gold edges, the record correctly has `system_answerable=insufficient` and non-empty `expected_uncertainties`. However, the `chain_complete` field must be present.

**Required fix**: Set `chain_complete=false` (the chain cannot be traced because the endpoint does not exist).

#### MAJOR -- Records 0015, 0016: Non-standard `stable_entity_key` format

Two gold_nodes use placeholder strings instead of SHA-256 hashes:

| Record | Node | Placeholder Key | Qualified Name |
|--------|------|----------------|----------------|
| 0015 | gold_nodes[0] | `phantom_frontend_0015` | GET /system/user/list |
| 0016 | gold_nodes[0] | `phantom_frontend_0016` | GET /system/role |

These nodes represent frontend_api_call entities that exist in source code but are not produced by the scanner (the JS/Vue parser does not generate `frontend_api_call` entities with the required start_line/end_line attributes). The placeholder keys are clearly intentional, and the source files do exist and contain the expected API calls.

However, the `stable_entity_key` field is defined as a SHA-256 hex digest. Placeholder strings violate the key format contract and will cause lookup failures in any code that assumes keys are 64-character hex strings.

**Required fix**: Either compute a proper stable_entity_key (requires assigning start_line/end_line to these frontend API call entities) or use a documented sentinel value that is still a valid SHA-256 hash (e.g., hash of a canonical placeholder string).

#### MINOR -- Records 0015, 0016: gold_nodes key not in gold_entities

The phantom frontend nodes appear in `gold_nodes` but not in `gold_entities`. This is structurally unusual but not necessarily incorrect -- the node represents a chain participant that the annotator could not fully annotate as a gold entity due to missing scanner output.

#### MINOR -- Record 0020: Non-empty `expected_uncertainties` for `system_answerable=full`

Three uncertainties are listed despite `system_answerable=full`. This contradicts the definition of "full" (all evidence available, no gaps). This is subsumed by the Critical finding above.

## 4. CODE_QA Spot Check Results

Four records audited: 0001 (zh, full), 0002 (en, full), 0008 (en, insufficient, source_answerable=false), 0009 (zh, insufficient, source_answerable=false).

| Record | Lang | system_answerable | Entities | Claims | Uncertainties | Status |
|--------|------|-------------------|----------|--------|---------------|--------|
| 0001 | zh | full | 2 | 2 | 0 | CLEAN |
| 0002 | en | full | 2 | 2 | 0 | CLEAN |
| 0008 | en | insufficient | 0 | 0 | 2 | CLEAN |
| 0009 | zh | insufficient | 0 | 0 | 2 | CLEAN |

All verified:
- Entity key recomputation: All 4 entity keys match.
- Snapshot presence: All indexed entities present in snapshot.
- File existence: All evidence files exist in repository.
- Uncertainty consistency: All partial/insufficient records have non-empty expected_uncertainties; all full records have empty expected_uncertainties.

**Result: All 4 CODE_QA spot checks PASS.**

## 5. CHANGE_PLAN Spot Check Results

Four records audited: 0025 (zh, full), 0026 (en, full), 0031 (zh, insufficient, source_answerable=false), 0034 (en, insufficient, source_answerable=false).

| Record | Lang | system_answerable | Entities | Files | Uncertainties | Status |
|--------|------|-------------------|----------|-------|---------------|--------|
| 0025 | zh | full | 2 | 5 | 0 | CLEAN |
| 0026 | en | full | 2 | 2 | 0 | CLEAN |
| 0031 | zh | insufficient | 0 | 0 | 2 | CLEAN |
| 0034 | en | insufficient | 0 | 0 | 2 | CLEAN |

All verified:
- Entity key recomputation: All 4 entity keys match.
- Snapshot presence: All indexed entities present in snapshot.
- File existence: All gold_files exist in repository.
- Uncertainty consistency: All partial/insufficient records have non-empty expected_uncertainties; all full records have empty expected_uncertainties.

**Result: All 4 CHANGE_PLAN spot checks PASS.**

## 6. Missing Key Classification Table

| # | Record | Qualified Name | File Path | Classification | Evidence |
|---|--------|---------------|-----------|----------------|----------|
| 1 | 0015 | GET /system/user/list | ruoyi-ui/src/api/system/user.js | legitimate_source_only | File exists; line 7: `url: '/system/user/list'` |
| 2 | 0016 | GET /system/role | ruoyi-ui/src/api/system/role.js | legitimate_source_only | File exists; URL path found |
| 3 | 0018 | GET /monitor/cache/getKeys/{cacheName} | ruoyi-ui/src/api/monitor/cache.js | legitimate_source_only | File exists; line 20: `url: '/monitor/cache/getKeys/' + cacheName` |
| 4 | 0022 | DELETE /system/user/{userIds} | ruoyi-ui/src/api/system/user.js | legitimate_source_only | File exists; line 41: `url: '/system/user/' + userId` with `method: 'delete'` |
| 5 | 0022 | GET /system/user/{userId} | ruoyi-ui/src/api/system/user.js | legitimate_source_only | File exists; line 16: `url: '/system/user/' + parseStrEmpty(userId)` |
| 6 | 0024 | GET /monitor/job/{jobId} | ruoyi-ui/src/api/monitor/job.js | legitimate_source_only | File exists; line 15: `url: '/monitor/job/' + jobId` |

| Classification | Count |
|---|---|
| Total missing keys (indexed_in_system=false) | 6 |
| legitimate_source_only | 6 |
| invalid_phantom_key | **0** |

All 6 missing keys are frontend_api_call entities in JavaScript files. The scanner's JS/Vue parser does not produce `frontend_api_call` entities with the attributes needed for stable key computation, so these entities exist in source code but cannot appear in the snapshot. The URLs are dynamically constructed via string concatenation, making static extraction difficult.

## 7. TRACE_CHAIN Consistency Statistics

### chain_complete distribution

| Value | Count | Records |
|-------|-------|---------|
| true | 5 | 0013, 0014, 0017, 0019, 0021 |
| false | 5 | 0015, 0016, 0018, 0022, 0024 |
| **MISSING** | **2** | **0020, 0023** |

### system_answerable distribution

| Value | Count | Records |
|-------|-------|---------|
| full | 6 | 0013, 0014, 0017, 0019, 0020, 0021 |
| partial | 3 | 0018, 0022, 0024 |
| insufficient | 3 | 0015, 0016, 0023 |

### Consistency matrix (system_answerable vs chain_complete)

| | chain_complete=true | chain_complete=false | chain_complete=MISSING |
|---|---|---|---|
| full | 5 (0013,0014,0017,0019,0021) | 0 | **1 (0020)** |
| partial | 0 | 3 (0018,0022,0024) | 0 |
| insufficient | 0 | 2 (0015,0016) | **1 (0023)** |

### Inconsistencies Found

| # | Severity | Record | Issue |
|---|----------|--------|-------|
| 1 | **Critical** | 0020 | `chain_complete` field missing from JSON |
| 2 | **Critical** | 0020 | `system_answerable=full` contradicts `source_answerable=false`, non-empty `expected_uncertainties`, and annotation notes ("Unanswerable trace") |
| 3 | **Critical** | 0023 | `chain_complete` field missing from JSON |
| 4 | Major | 0015 | Non-standard `stable_entity_key` format (placeholder string) |
| 5 | Major | 0016 | Non-standard `stable_entity_key` format (placeholder string) |
| 6 | Minor | 0015 | gold_nodes[0] key not in gold_entities |
| 7 | Minor | 0016 | gold_nodes[0] key not in gold_entities |

## 8. Final Verdict

### **NOT READY**

**Reason**: 3 Critical inconsistencies found.

| Blocking Issue | Record | Required Action |
|---|---|---|
| Missing `chain_complete` field | 0020 | Add `chain_complete: false` |
| `system_answerable` contradiction | 0020 | Change to `partial` or `insufficient` |
| Missing `chain_complete` field | 0023 | Add `chain_complete: false` |

### Non-blocking Issues (should fix before Stage 2B)

| Issue | Records | Recommended Action |
|---|---|---|
| Non-standard key format | 0015, 0016 | Compute proper SHA-256 keys or adopt documented sentinel convention |

### After fixes, re-verify:
1. Record 0020: chain_complete=false, system_answerable=insufficient, expected_uncertainties non-empty
2. Record 0023: chain_complete=false
3. All 12 TRACE_CHAIN records have the `chain_complete` field present
4. No record with system_answerable=full has non-empty expected_uncertainties
