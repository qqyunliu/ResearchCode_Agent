# SUPERSEDED -- Audited the pre-fix 42-record dataset

**Status:** This blind audit report has been SUPERSEDED.
**Reason:** Audited the 42-record `pilot.jsonl` dataset (v1.2) that included
6 historical change cases mixed with 36 synthetic questions. The dataset has
since been split into `pilot-current.jsonl` (36 records) and
`historical-prepared.jsonl` (6 records) as part of Stage 2A.2.
**Findings about frontend entity key mismatch (Critical) remain valid** and
apply to the current 36-record dataset as well.
**Current valid report:** `evaluation/reports/stage2a2-final-report.md`

---

# Blind Audit Report: pilot.jsonl Dataset

**Auditor:** audit_agent_E (Independent Blind Auditor)
**Date:** 2026-07-15
**Dataset:** `evaluation/datasets/pilot.jsonl` (v1.2, 42 records)
**Repository:** `ruoyi-vue` at commit `41720e624c5a668c7d3777835e4c87095a7a1dfd`
**Snapshot:** `evaluation/runtime/pilot/snapshot/` (2199 entities, 1980 relations)

---

## 1. Sampling Method

Stratified sampling of **12 records** from 42 total, covering all required strata:

| # | Line | question_id | task_type | lang | difficulty | source_answerable | system_answerable |
|---|------|-------------|-----------|------|------------|-------------------|-------------------|
| 1 | 1 | ruoyi-code-qa-0001 | CODE_QA | zh | easy | true | full |
| 2 | 2 | ruoyi-code-qa-0002 | CODE_QA | en | easy | true | full |
| 3 | 8 | ruoyi-code-qa-0008 | CODE_QA | en | medium | false | insufficient |
| 4 | 9 | ruoyi-code-qa-0009 | CODE_QA | zh | medium | false | insufficient |
| 5 | 13 | ruoyi-trace-chain-0013 | TRACE_CHAIN | zh | easy | true | full |
| 6 | 16 | ruoyi-trace-chain-0016 | TRACE_CHAIN | en | medium | true | insufficient |
| 7 | 21 | ruoyi-trace-chain-0021 | TRACE_CHAIN | zh | hard | true | full |
| 8 | 24 | ruoyi-trace-chain-0024 | TRACE_CHAIN | en | hard | false | insufficient |
| 9 | 25 | ruoyi-change-plan-0025 | CHANGE_PLAN | zh | easy | true | full |
| 10 | 31 | ruoyi-change-plan-0031 | CHANGE_PLAN | zh | medium | false | insufficient |
| 11 | 32 | ruoyi-change-plan-0032 | CHANGE_PLAN | en | hard | true | full |
| 12 | 34 | ruoyi-change-plan-0034 | CHANGE_PLAN | en | hard | false | insufficient |

**Strata coverage:**
- CODE_QA: 4 (min 2 required)
- TRACE_CHAIN: 4 (min 2 required)
- CHANGE_PLAN: 4 (min 2 required)
- Chinese: 6 (min 2 required)
- English: 6 (min 2 required)
- Easy: 3, Medium: 3, Hard: 4 (min 1 each required)
- source_answerable=false: 5 (min 2 required)
- system_answerable=insufficient: 6 (min 2 required)

---

## 2. Per-Record Audit Results

### Record 1: ruoyi-code-qa-0001 (CODE_QA, zh, easy)

**Question:** "用户登录的接口定义在哪个控制器中，该接口的HTTP方法和路径是什么？"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | zh, 82.4% CJK - correct | OK |
| 2. File paths | SysLoginController.java exists | OK |
| 3. Line numbers | Class at 32-138 (annotation+class to closing brace) - correct; method login at 56-65 (`@PostMapping("/login")` to `}`) - correct | OK |
| 4. Stable keys | Both keys verified by recomputation | OK |
| 5. Required claims | Claim 1: "登录接口在SysLoginController中定义" - line 56-65 has `@PostMapping("/login") public AjaxResult login(...)` - correct. Claim 2: "HTTP方法为POST，路径为/login" - line 56 has `@PostMapping("/login")` - correct | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | Source code matches gold | OK |
| 8. Indexed observation | No gold_edges | OK |
| 9. Answer leakage | No class/method names in question text | OK |
| 10. Alternative answers | No alternative login controllers exist | OK |

**Findings:** None. Clean record.

---

### Record 2: ruoyi-code-qa-0002 (CODE_QA, en, easy)

**Question:** "Which controller handles the user list query API, and what is its request mapping path prefix?"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | en, 0% CJK - correct | OK |
| 2. File paths | SysUserController.java exists | OK |
| 3. Line numbers | Class at 40-256 (`@RestController` to `}`) - correct; method list at 59-66 (`@PreAuthorize` to `}`) - correct | OK |
| 4. Stable keys | Both keys verified | OK |
| 5. Required claims | Claim 1: SysUserController handles user list - line 59-66 shows `@GetMapping("/list") public TableDataInfo list(SysUser user)` - correct. Claim 2: class-level RequestMapping is /system/user - line 41 `@RequestMapping("/system/user")` - correct | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | Source matches gold | OK |
| 8. Indexed observation | No gold_edges | OK |
| 9. Answer leakage | No specific class names in question | OK |
| 10. Alternative answers | SysProfileController exists at /system/user/profile but handles profile, not list queries. Gold is correct | OK |

**Findings:** None. Clean record.

---

### Record 3: ruoyi-code-qa-0008 (CODE_QA, en, medium, unanswerable)

**Question:** "Is there a dedicated API for batch-importing user data from a JSON file? Which endpoint accepts JSON-format user imports?"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | en, 0% CJK - correct | OK |
| 2. File paths | SysUserController.java (in provenance) exists | OK |
| 3. Line numbers | Provenance references lines 78-88 (importData method using ExcelUtil with MultipartFile) - verified | OK |
| 4. Stable keys | No gold_entities (correct for unanswerable) | OK |
| 5. Required claims | None (correct - unanswerable) | OK |
| 6. Forbidden claims | Claim 1: "There is a JSON batch import endpoint" - reason: system only supports Excel import via POST /system/user/importData with MultipartFile. VERIFIED correct (line 80-88 uses ExcelUtil.importExcel). Claim 2: "Any endpoint accepts JSON for user import" - VERIFIED correct | OK |
| 7. Source truth | Source confirms Excel-only import. Unanswerable label correct | OK |
| 8. Indexed observation | N/A | OK |
| 9. Answer leakage | No leakage | OK |
| 10. Alternative answers | N/A for unanswerable | OK |

**Findings:** None. Well-designed unanswerable question.

---

### Record 4: ruoyi-code-qa-0009 (CODE_QA, zh, medium, unanswerable)

**Question:** "系统中是否存在短信发送功能的API接口？如果有，说明其实现位置。"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | zh, 82.4% CJK - correct | OK |
| 2. File paths | No source files (correct for unanswerable with no relevant code) | OK |
| 3. Line numbers | N/A | OK |
| 4. Stable keys | No gold_entities | OK |
| 5. Required claims | None | OK |
| 6. Forbidden claims | 2 forbidden claims about SMS API existence - correct (no SMS feature in RuoYi-Vue base) | OK |
| 7. Source truth | Verified: no SMS-related controllers, services, or utilities exist in the codebase | OK |
| 8. Indexed observation | N/A | OK |
| 9. Answer leakage | No leakage | OK |
| 10. Alternative answers | N/A | OK |

**Findings:** None. Clean unanswerable record.

---

### Record 5: ruoyi-trace-chain-0013 (TRACE_CHAIN, zh, easy)

**Question:** "前端调用登录接口POST /login时，请求从前端到后端的哪个控制器，再到哪个服务方法？"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | zh, 70.0% CJK - correct | OK |
| 2. File paths | login.js and SysLoginController.java both exist | OK |
| 3. Line numbers | login.js lines 4-20 (function definition) - correct; SysLoginController.login lines 56-65 - correct | OK |
| 4. Stable keys | Both gold_entity keys verified by recomputation | OK |
| 5. Required claims | Claim: "前端login.js的POST /login请求到达SysLoginController.login方法" - evidence at login.js:11-19 (the request call) and SysLoginController.java:56-65 - correct | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | Source code matches all claims | OK |
| 8. Indexed observation | **CRITICAL** - see finding below | **CRITICAL** |
| 9. Answer leakage | Question mentions "POST /login" (the API path) - this is the INPUT to the trace, not the answer. No leakage | OK |
| 10. Alternative answers | No alternative handler for POST /login | OK |

**CRITICAL FINDING - Entity key mismatch with snapshot:**

The gold_entities use `qualified_name: "login"` (function name) and lines 4-20 (function definition range) for the frontend entity. The snapshot's `code_entities.json` indexes this same code as `qualified_name: "POST /login"` (HTTP method + URL) at lines 11-19 (the request call range). This produces **different stable_entity_keys**:
- Gold key: `9b385d5558e809ef9dc017d36c3643e77abfbf9eff03deb639aee1eab1ab9db7`
- Snapshot key: `533e441b35ffa64174a6ecb57519c8344e1a109d89c37e4e2c39b2b4dd7e6f2d`

Similarly, the gold_edge targets `SysLoginController.login` (entity_type: `java_method`, key: `799e8cba...`), but the snapshot's REQUESTS_API relation targets `POST /login` (entity_type: `backend_api`, key: `8af86132...`). The scanner creates **two separate entities** for each API method: a `java_method` and a `backend_api`, connected by a `DEFINES_API` relation. The REQUESTS_API chain is:

```
frontend_api_call --[REQUESTS_API]--> backend_api --[DEFINES_API]--> java_method
```

The gold assumes a simpler model:
```
frontend_api_call --[REQUESTS_API]--> java_method
```

**Impact:**
- The gold_entity key for the frontend call will NEVER match any snapshot entity
- The gold_edge REQUESTS_API target (java_method) is NOT the target of any REQUESTS_API relation in the system (all 79 REQUESTS_API relations connect to backend_api, not java_method)
- The `indexed_in_system: false` label is technically correct, but the reason is structural (key mismatch), not just that the relation is missing
- If evaluation checks stable_entity_keys, these will be phantom misses

**Recommendation:** Gold entities for frontend_api_call should either use the scanner's qualified_name convention ("POST /login" instead of "login") and line ranges, or the evaluation framework must implement key equivalence mapping between java_method and backend_api entities.

---

### Record 6: ruoyi-trace-chain-0016 (TRACE_CHAIN, en, medium)

**Question:** "When the frontend calls PUT /system/role to update a role, which controller method handles it and which service method does it invoke? Also, what additional action is taken after a successful update?"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | en, 0% CJK - correct | OK |
| 2. File paths | SysRoleController.java exists | OK |
| 3. Line numbers | edit method at 110-134 - verified: `@PreAuthorize` through closing `}` | OK |
| 4. Stable keys | Key verified for SysRoleController.edit | OK |
| 5. Required claims | Claim 1: edit handles PUT /system/role - line 112 `@PutMapping` with class-level `@RequestMapping("/system/role")` at line 38 - correct. Claim 2: calls roleService.updateRole - line 127 `roleService.updateRole(role)` - correct. Claim 3: calls tokenService.refreshPermissionByRoleId - line 130 - correct | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | All 3 claims verified against source | OK |
| 8. Indexed observation | No gold_edges. system_answerable=insufficient due to CALLS_METHOD not indexed - correct. expected_uncertainties correctly notes CALLS_METHOD gap | OK |
| 9. Answer leakage | Question mentions "PUT /system/role" - this is the input (API path). No class/method names leaked | OK |
| 10. Alternative answers | No alternative edit handler for PUT /system/role | OK |

**Findings:** None. Well-structured trace record with correct uncertainty annotations.

---

### Record 7: ruoyi-trace-chain-0021 (TRACE_CHAIN, zh, hard)

**Question:** "系统中存在多个名为getInfo的方法，分别在哪些控制器中定义？它们各自对应的API路径是什么？前端调用GET /getInfo时会到达哪个控制器？"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | zh, 65.3% CJK - correct | OK |
| 2. File paths | SysLoginController.java, CacheController.java, SysUserController.java, login.js - all exist | OK |
| 3. Line numbers | SysLoginController.getInfo 72-94 - correct (`@GetMapping("getInfo")` through `}`); CacheController.getInfo 48-71 - correct (`@SuppressWarnings` through `}`); SysUserController.getInfo 100-117 - correct (`@PreAuthorize` through `}`) | OK |
| 4. Stable keys | All 3 gold_entity keys verified | OK |
| 5. Required claims | Claim 1: SysLoginController.getInfo maps GET /getInfo - line 72 `@GetMapping("getInfo")` - correct. Claim 2: CacheController.getInfo maps GET /monitor/cache - class has `@RequestMapping("/monitor/cache")` + `@GetMapping()` - correct. Claim 3: SysUserController.getInfo maps GET /system/user/{userId} - class has `@RequestMapping("/system/user")` + `@GetMapping(value = { "/", "/{userId}" })` - correct | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | All three getInfo methods and their API paths verified | OK |
| 8. Indexed observation | **CRITICAL** - same entity key mismatch as record 13 for the frontend getInfo node (key `352ddecf...` not in snapshot) | **CRITICAL** |
| 9. Answer leakage | Question mentions "getInfo" by name. However, this is **intentional and necessary** - the question is specifically about disambiguating same-name methods. The method name IS the question input, not the answer. Acceptable | OK |
| 10. Alternative answers | Gold correctly enumerates all 3 getInfo methods. No missing alternatives | OK |

**CRITICAL FINDING:** Same frontend_api_call key mismatch as record 13. The gold_nodes include `getInfo` (frontend_api_call, key `352ddecf...`) which doesn't match the snapshot's `GET /getInfo` (key `0bc05518...`). The gold_edge connects this non-matching frontend key to SysLoginController.getInfo (java_method key), but the system's REQUESTS_API connects to backend_api, not java_method.

---

### Record 8: ruoyi-trace-chain-0024 (TRACE_CHAIN, en, hard, unanswerable)

**Question:** "The frontend job module calls a function to get job details by ID using a dynamically constructed URL. Can you trace this specific frontend request through the REQUESTS_API relation in the static index to its backend handler?"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | en, 0% CJK - correct | OK |
| 2. File paths | job.js and SysJobController.java both exist | OK |
| 3. Line numbers | getJob at job.js:13-18 - verified: `export function getJob(jobId)` with `url: '/monitor/job/' + jobId`. SysJobController.getInfo at 70-75 - verified | OK |
| 4. Stable keys | Both keys verified by recomputation | OK |
| 5. Required claims | None (correct - unanswerable through index) | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | Dynamic URL confirmed: `url: '/monitor/job/' + jobId` at line 15. Backend SysJobController has `@GetMapping(value = "/{jobId}")` at line 71 - correct | OK |
| 8. Indexed observation | getJob (key `2773726...`) NOT in code_entities.json - confirmed (dynamic URL means scanner skipped it) | OK |
| 9. Answer leakage | No leakage | OK |
| 10. Alternative answers | N/A | OK |

**MINOR FINDING:** `source_answerable=false` but gold_entities has 2 entities. The entities serve as reference for evaluation, not as answerable gold. This is a design choice for unanswerable trace records. The inconsistency is noted but acceptable since the question is about index-based tracing (which fails due to dynamic URL), not about whether the code exists.

---

### Record 9: ruoyi-change-plan-0025 (CHANGE_PLAN, zh, easy)

**Question:** "假如要在通知管理模块中添加一个"置顶消息"的功能，需要修改哪些文件？请列出后端控制器、服务接口、服务实现、实体类和前端API文件。"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | zh, 83.9% CJK - correct | OK |
| 2. File paths | All 5 gold_files verified: SysNoticeController.java, ISysNoticeService.java, SysNoticeServiceImpl.java, SysNotice.java, notice.js - all exist | OK |
| 3. Line numbers | SysNoticeController class at 31-150 - correct; list method at 44-51 - correct | OK |
| 4. Stable keys | Both gold_entity keys verified | OK |
| 5. Required claims | Claim 1: modify SysNoticeController to add endpoint - correct (existing controller has CRUD, needs pin endpoint). Claim 2: add to ISysNoticeService interface - correct | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | SysNoticeController has list/getInfo/add/edit/remove - no pin/top feature exists. Change plan is reasonable | OK |
| 8. Indexed observation | No gold_edges | OK |
| 9. Answer leakage | Question mentions "通知管理模块" (notice module) generically, not specific class names. Acceptable | OK |
| 10. Alternative answers | gold_files include SysNoticeReadServiceImpl is not listed but might also need changes. Minor - the listed files are the primary ones | OK |

**Findings:** None. Well-structured hypothetical change plan.

---

### Record 10: ruoyi-change-plan-0031 (CHANGE_PLAN, zh, medium, unanswerable)

**Question:** "我要优化系统的查询性能，应该从哪些部分入手？需要修改哪些核心文件？"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | zh, 91.2% CJK - correct | OK |
| 2. File paths | No source files (correct for vague unanswerable) | OK |
| 3. Line numbers | N/A | OK |
| 4. Stable keys | No gold_entities | OK |
| 5. Required claims | None | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | Question is too vague to have a definitive answer - "查询性能优化" could mean database queries, search, caching, etc. | OK |
| 8. Indexed observation | N/A | OK |
| 9. Answer leakage | No leakage | OK |
| 10. Alternative answers | N/A | OK |

**Findings:** None. Correctly identified as unanswerable due to vague scope.

---

### Record 11: ruoyi-change-plan-0032 (CHANGE_PLAN, en, hard)

**Question:** "To implement real-time WebSocket-based notification delivery for the notice module (so users get instant updates when new notices are published), what changes would be needed across the backend and frontend? Consider the existing notice architecture."

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | en, 0% CJK - correct | OK |
| 2. File paths | All 4 gold_files verified: SysNoticeController.java, SysNoticeServiceImpl.java, SysNoticeReadServiceImpl.java, notice.js - all exist | OK |
| 3. Line numbers | Same SysNoticeController entities as record 25 - verified | OK |
| 4. Stable keys | Both gold_entity keys verified (same as record 25) | OK |
| 5. Required claims | Claim: "Backend needs WebSocket configuration and event publishing" - reasonable given existing architecture | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | SysNoticeController exists with CRUD. SysNoticeReadServiceImpl exists for read tracking. WebSocket would be a cross-cutting addition. Reasonable | OK |
| 8. Indexed observation | N/A | OK |
| 9. Answer leakage | Question mentions "notice module" generically. No specific class names leaked | OK |
| 10. Alternative answers | SecurityConfig.java is in provenance but not gold_files. Could be needed for WebSocket security. Minor consideration | OK |

**Findings:** None. Well-designed hard hypothetical change plan.

---

### Record 12: ruoyi-change-plan-0034 (CHANGE_PLAN, en, hard, unanswerable)

**Question:** "If we wanted to migrate the entire RuoYi-Vue backend from Spring Boot to Quarkus framework, what would be the complete list of files that need to be rewritten?"

| Check | Result | Severity |
|-------|--------|----------|
| 1. Language | en, 0% CJK - correct | OK |
| 2. File paths | No source files (correct) | OK |
| 3. Line numbers | N/A | OK |
| 4. Stable keys | No gold_entities | OK |
| 5. Required claims | None | OK |
| 6. Forbidden claims | None | OK |
| 7. Source truth | Full framework migration would affect virtually all Java files - scope too large to enumerate | OK |
| 8. Indexed observation | N/A | OK |
| 9. Answer leakage | Question mentions "RuoYi-Vue" and "Spring Boot to Quarkus" - these are the scope descriptors, not answers | OK |
| 10. Alternative answers | N/A | OK |

**Findings:** None. Correctly identified as unanswerable due to scope.

---

## 3. Summary

### Issue Counts

| Severity | Count | Details |
|----------|-------|---------|
| **CRITICAL** | **2** | Frontend_api_call entity key mismatch in records 13 and 21 |
| **MAJOR** | **0** | - |
| **MINOR** | **1** | Record 24: source_answerable=false with gold_entities (design choice) |

### Critical Issue Detail

**Systematic: Frontend entity identification mismatch between gold labels and scanner**

Affected records: 13 (ruoyi-trace-chain-0013), 21 (ruoyi-trace-chain-0021), and potentially 24 (ruoyi-trace-chain-0024).

The scanner's `code_entities.json` uses:
- `qualified_name`: HTTP method + URL path (e.g., `"POST /login"`, `"GET /getInfo"`)
- `start_line/end_line`: The `request()` call block (e.g., lines 11-19)

The gold labels use:
- `qualified_name`: JavaScript function name (e.g., `"login"`, `"getInfo"`)
- `start_line/end_line`: The function definition block (e.g., lines 4-20)

This produces different `stable_entity_key` values, meaning gold entities for frontend_api_call will never match any entity in the system's index.

Additionally, the scanner's `REQUESTS_API` relations connect `frontend_api_call -> backend_api` (79 relations, 100%), while gold edges assume `frontend_api_call -> java_method`. The system has a 2-hop chain:
```
frontend_api_call --[REQUESTS_API]--> backend_api --[DEFINES_API]--> java_method
```
but the gold assumes a 1-hop model.

**Impact on evaluation:**
1. Retrieval evaluation: Frontend entities scored as misses even if correctly retrieved (key mismatch)
2. Graph traversal evaluation: Gold edges unmatchable because target keys differ
3. The `indexed_in_system: false` labels are technically correct but mask the structural nature of the mismatch

**Affected records in full dataset:** All TRACE_CHAIN records with gold_entities or gold_edges involving `frontend_api_call` entities. From the dataset overview, this likely includes records 13-24 (12 records).

### Recommended Corrections

1. **[CRITICAL] Reconcile frontend entity naming:** Gold labels should use the scanner's qualified_name convention (`"POST /login"` not `"login"`) and corresponding line ranges, OR the evaluation framework should implement an equivalence layer that maps between function-name and HTTP-method-URL conventions.

2. **[CRITICAL] Align gold_edge targets:** For TRACE_CHAIN records with gold_edges using REQUESTS_API, the target should reference the `backend_api` entity (which is what the system actually connects), not the `java_method` entity. Alternatively, gold_edges should include both the REQUESTS_API hop (frontend -> backend_api) and the DEFINES_API hop (backend_api -> java_method).

3. **[MINOR] Clarify source_answerable for record 24:** Consider adding a note that gold_entities are provided for partial evaluation reference despite source_answerable=false.

---

## 4. Expansion Recommendation

The Critical error rate among audited records is **2/12 = 16.7%**, and both Critical errors stem from the same systematic issue (frontend entity key mismatch). This issue likely affects **all TRACE_CHAIN records with frontend entities** (estimated 8-12 records from the full 42).

**Recommendation:** **Expand audit to all TRACE_CHAIN records** (records 13-24, 12 total) to confirm the scope of the frontend entity mismatch. If confirmed, apply a batch correction to all affected records before Stage 2B proceeds.

CODE_QA and CHANGE_PLAN records appear clean and do not require expansion.

---

## 5. Auditor Certification

I, audit_agent_E, certify that:
- I did NOT read any B0/B1 baseline results, canonical report conclusions, or annotator reasoning
- I verified all findings against the actual source code at the specified commit
- I recomputed all stable_entity_keys independently
- I checked all file paths against the repository filesystem
- I read and verified all cited line ranges in source files
- I cross-referenced gold edges against the snapshot's code_relations.json

The dataset is **conditionally ready** for Stage 2B, pending resolution of the frontend entity key mismatch issue in TRACE_CHAIN records.
