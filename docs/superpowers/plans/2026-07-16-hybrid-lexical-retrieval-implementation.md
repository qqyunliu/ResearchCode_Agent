# Hybrid Lexical Retrieval Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the keyword branch interpret rewritten natural-language code queries as bounded code-aware terms so hybrid retrieval has measurable lexical contribution without changing the frozen 0.7/0.3 fusion weights.

**Architecture:** Add a deterministic lexical parser in the retrieval layer, then make `KeywordSearchService` perform one project-scoped multi-term candidate query and deterministic coverage/field ranking. Preserve the public search contract and exact structured-query behavior. Add evaluation-only branch diagnostics and write all post-fix results under a new identity so Stage 2B remains frozen.

**Tech Stack:** Python 3.11, SQLAlchemy 2, SQLite, pytest, existing Qdrant/OpenAI-compatible retrieval runtime.

---

## File map

- Create `backend/app/retrieval/lexical_query.py`: deterministic code-aware term parsing only.
- Create `backend/tests/unit/test_lexical_query.py`: parser contract and bounds.
- Modify `backend/app/retrieval/keyword_search.py`: one-query multi-term candidate retrieval and ranking.
- Modify `backend/tests/integration/test_keyword_search.py`: database-backed behavioral regressions.
- Modify `backend/tests/unit/test_hybrid_search.py`: prove lexical candidates can affect unchanged 0.7/0.3 fusion.
- Modify `evaluation/runners/stage2b_retrieval.py`: record branch hit/overlap/ranking-change diagnostics and support an explicitly selected post-fix variant set without changing the default Stage 2B schedule.
- Modify `evaluation/scripts/tests/test_stage2b_retrieval.py`: runner diagnostics, selection, identity, and resume tests.
- Create `evaluation/reports/hybrid-lexical-repair-report.md` only after the post-fix run: measured comparison and claim boundary.

### Task 1: Code-aware lexical query parser

**Files:**
- Create: `backend/app/retrieval/lexical_query.py`
- Create: `backend/tests/unit/test_lexical_query.py`

- [ ] **Step 1: Write failing parser tests**

Cover these exact behaviors:

```python
from app.retrieval.lexical_query import parse_lexical_terms


def test_parses_natural_language_without_repository_vocabulary():
    assert parse_lexical_terms("user login controller HTTP method path") == (
        "user", "login", "controller", "http", "method", "path"
    )


def test_preserves_paths_and_splits_identifiers():
    terms = parse_lexical_terms("Find SysUserController.getUserProfile at /system/user")
    assert "/system/user" in terms
    assert "sysusercontroller.getuserprofile" in terms
    assert {"sys", "user", "controller", "get", "profile"} <= set(terms)


def test_filters_language_stop_words_and_deduplicates():
    assert parse_lexical_terms("where is the user user endpoint") == (
        "user", "endpoint"
    )


def test_empty_or_stopword_only_query_has_no_terms():
    assert parse_lexical_terms("where is the") == ()


def test_term_count_is_bounded_deterministically():
    query = " ".join(f"term{index}" for index in range(20))
    assert parse_lexical_terms(query, max_terms=12) == tuple(
        f"term{index}" for index in range(12)
    )
```

- [ ] **Step 2: Run the parser tests and verify RED**

Run from `backend/`:

```powershell
.\.venv\python.exe -m pytest tests\unit\test_lexical_query.py -q
```

Expected: collection/import failure because `app.retrieval.lexical_query` does not exist.

- [ ] **Step 3: Implement the minimal parser**

Implement this public contract:

```python
DEFAULT_MAX_TERMS = 12


def parse_lexical_terms(
    query: str,
    *,
    max_terms: int = DEFAULT_MAX_TERMS,
) -> tuple[str, ...]:
    """Return ordered, de-duplicated code-aware lexical terms."""
```

Implementation rules:

- use compiled regular expressions for paths/ASCII compound boundaries and
  standard-library `unicodedata` category checks for Unicode identifier
  scanning; add no third-party dependency;
- extract API paths before ordinary words;
- preserve dotted/camel/snake structured identifiers and add their components;
- case-fold all terms;
- filter a fixed English language stop-word set such as `the`, `is`, `where`,
  `which`, `what`, `and`, `for`, `to`, `of`, `in`, `at`, `a`, `an`;
- do not filter code-domain words such as `controller`, `api`, `method`, or
  `path` in this stage;
- retain CJK chunks when rewriting is unavailable;
- retain standalone `$` and non-composable Unicode combining marks that are
  valid identifier continuations;
- reject `max_terms < 1` with `ValueError`;
- stop after the first `max_terms` unique terms.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run the Step 2 command. Expected: all parser tests pass.

### Task 2: Multi-term keyword candidate retrieval

**Files:**
- Modify: `backend/app/retrieval/keyword_search.py`
- Modify: `backend/tests/integration/test_keyword_search.py`

- [ ] **Step 1: Write failing database-backed tests**

Add cases proving:

```python
def test_natural_language_query_matches_distinct_terms(session, indexed_project):
    hits = KeywordSearchService(session).search(
        indexed_project.id,
        "user login controller HTTP method path",
        10,
    )
    assert hits
    assert any("login" in hit.qualified_name.casefold() for hit in hits)


def test_stopword_only_query_returns_no_hits(session, indexed_project):
    assert KeywordSearchService(session).search(
        indexed_project.id, "where is the", 10
    ) == []


def test_multi_term_ranking_rewards_distinct_coverage(session, indexed_project):
    hits = KeywordSearchService(session).search(
        indexed_project.id, "user login", 10
    )
    assert hits[0].score > 0
    assert "user" in (
        hits[0].name + hits[0].qualified_name + hits[0].content
    ).casefold()
    assert "login" in (
        hits[0].name + hits[0].qualified_name + hits[0].content
    ).casefold()


def test_domain_terms_outrank_generic_structural_decoy(...): ...
def test_sql_orders_and_limits_before_orm_materialization(...): ...
def test_sqlite_search_normalizes_nfc_and_casefold(...): ...
def test_complete_structured_value_precedes_component_fallback(...): ...
```

Keep or extend existing exact identifier, API path, wildcard escaping, project
isolation, limit, and deterministic-order tests.

- [ ] **Step 2: Run the selected tests and verify RED**

```powershell
.\.venv\python.exe -m pytest tests\integration\test_keyword_search.py -q
```

Expected: the new natural-language and stopword tests fail under whole-phrase
matching.

- [ ] **Step 3: Implement bounded SQL-side lexical ranking**

Register a deterministic lexical-score UDF on the active SQLite connection.
Pass the five searchable fields to it, order in SQL by score descending and
entity ID ascending, and apply `LIMIT` before materializing ORM entities. The
scorer must NFC-normalize and casefold both query terms and stored values.

- [ ] **Step 4: Implement deterministic multi-term scoring**

Keep the existing field priority as the per-term signal. For multi-term queries,
weight low-information structural terms (`controller`, `api`, `method`, `path`,
`file`, `class`, `endpoint`, `http`, `code`, and `module`) at 0.25 and all
other terms at 1.0. Score with:

```python
score = (
    0.6 * matched_weight / total_weight
    + 0.4 * weighted_field_signal / total_weight
)
```

A complete structured identifier, filename, or path match takes priority;
component fallback is used only when the complete value has no match. Single-
term scores and ordering remain backward compatible. Do not change `SearchHit`
or API response schemas.

- [ ] **Step 5: Run keyword tests and the focused backend retrieval suite**

```powershell
.\.venv\python.exe -m pytest tests\integration\test_keyword_search.py tests\unit\test_hybrid_search.py -q
```

Expected: all selected tests pass.

### Task 3: Prove unchanged fusion can use lexical contribution

**Files:**
- Modify: `backend/tests/unit/test_hybrid_search.py`
- No production change expected in `backend/app/retrieval/hybrid_search.py`

- [ ] **Step 1: Add a fusion regression test**

Construct vector hits `[entity 1, entity 2]` and lexical hits containing entity
2 plus entity 3. Assert entity 2 moves ahead because it receives both the fixed
0.7 vector contribution and fixed 0.3 keyword contribution. Also assert a
keyword-only entity remains eligible.

- [ ] **Step 2: Run the test and verify current fusion is already GREEN**

```powershell
.\.venv\python.exe -m pytest tests\unit\test_hybrid_search.py -q
```

Expected: pass. This is a characterization test showing no fusion-code change
is necessary once lexical hits exist.

- [ ] **Step 3: Confirm the production weights remain unchanged**

```powershell
rg -n "0\.7|0\.3" app\retrieval\hybrid_search.py
```

Expected: the existing fixed weights remain the only production weights.

### Task 4: Add post-fix branch observability and isolated variant execution

**Files:**
- Modify: `evaluation/runners/stage2b_retrieval.py`
- Modify: `evaluation/scripts/tests/test_stage2b_retrieval.py`

- [ ] **Step 1: Write failing diagnostics and selection tests**

Require each selected hybrid record to include:

```json
{
  "branch_diagnostics": {
    "vector_candidate_count": 20,
    "keyword_candidate_count": 7,
    "overlap_count": 3,
    "keyword_only_count": 4,
    "top10_changed_from_vector": true
  }
}
```

Add CLI/schedule tests for an explicit selection such as
`--variants B2,B3,A1,A2,A3,A4`. The default with no option must remain the exact
existing nine-variant Stage 2B schedule. Selected variants, their order, and a
lexical implementation version string must enter the run/config fingerprint so
old checkpoints cannot be reused silently.

- [ ] **Step 2: Run focused tests and verify RED**

From the repository root:

```powershell
.\backend\.venv\python.exe -m pytest evaluation\scripts\tests\test_stage2b_retrieval.py -q
```

Expected: failures for the missing CLI selection and branch diagnostics.

- [ ] **Step 3: Implement selected-variant schedule and diagnostics**

Add a parsed, validated variant list with duplicate/unknown rejection. Compute
diagnostics from the same vector and keyword candidate lists used for fusion;
do not make a second embedding or rewrite call. Use stable entity keys when
comparing overlap and ranking. Keep default output and formal Stage 2B behavior
unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all Stage 2B retrieval tests pass.

### Task 5: Regression verification before real evaluation

**Files:**
- No new files

- [ ] **Step 1: Run backend retrieval tests**

```powershell
cd backend
.\.venv\python.exe -m pytest tests\unit\test_lexical_query.py tests\unit\test_hybrid_search.py tests\integration\test_keyword_search.py tests\integration\test_hybrid_search_api.py -q
```

Expected: all pass.

- [ ] **Step 2: Run full backend tests**

```powershell
.\.venv\python.exe -m pytest -q
```

Expected: all pass except documented skips.

- [ ] **Step 3: Run full evaluation tests and compilation**

```powershell
cd ..
.\backend\.venv\python.exe -m pytest evaluation\scripts\tests -q
.\backend\.venv\python.exe -m compileall -q backend\app evaluation\runners evaluation\scripts
git diff --check
```

Expected: all tests and compilation pass; diff check has no patch errors.

### Task 6: Run isolated post-fix retrieval evaluation

**Files:**
- Create: `evaluation/results/raw/hybrid_lexical_v2_retrieval.jsonl`
- Create: `evaluation/results/raw/hybrid_lexical_v2_retrieval.metadata.json`
- Create: `evaluation/results/metrics/hybrid_lexical_v2_metrics.json`
- Create: `evaluation/reports/hybrid-lexical-repair-report.md`

- [ ] **Step 1: Request explicit permission for real provider calls**

Explain that the selected B2/B3/A1-A4 run may call the configured embedding and
rewrite providers. Offer a lower-cost alternative using only deterministic
backend fixtures, which cannot establish the real Recall@10 gate.

- [ ] **Step 2: Run selected variants under a new identity**

Use the frozen dataset SHA, repository commit, snapshot attestation, existing
isolated DB/Qdrant, a new run ID, and the new output paths. Never use the frozen
Stage 2B output path. Run from the repository root:

```powershell
.\backend\.venv\python.exe evaluation\runners\stage2b_retrieval.py `
  --phase run `
  --variants B2,B3,A1,A2,A3,A4 `
  --dataset evaluation\datasets\pilot-current.jsonl `
  --dataset-sha 86ffda7cf4b90eabfaf5d44dff6b76a9f841fe7e6e9bcb8df6cae1e8fac8d65c `
  --repo-commit 41720e624c5a668c7d3777835e4c87095a7a1dfd `
  --snapshot evaluation\runtime\pilot\snapshot-v3\manifest.json `
  --db evaluation\runtime\pilot\rca_eval.db `
  --qdrant-path evaluation\runtime\pilot\stage2b_qdrant `
  --output evaluation\results\raw\hybrid_lexical_v2_retrieval.jsonl `
  --metadata evaluation\results\raw\hybrid_lexical_v2_retrieval.metadata.json `
  --ledger-dir evaluation\runtime\pilot\hybrid_lexical_v2_provider_ledgers
```

Expected: exit 0 with 216 records (36 questions times 6 selected variants), a
new completed metadata file, and no writes to `stage2b_retrieval.jsonl`.

- [ ] **Step 3: Validate raw identity and contribution**

Fail closed unless the selected schedule is exact, all records are unique and
`status=ok`, metadata is completed, provider ledgers have no pending/orphan
attempts, and branch diagnostics are present for every hybrid variant.

- [ ] **Step 4: Compute comparison metrics**

Report at minimum:

- B1/B2/B3 File Recall@1/5/10, MRR, and zero-hit on the same 27 indexed
  must-recall cases;
- keyword nonzero-hit rate;
- mean keyword candidate count;
- mean vector/keyword overlap;
- keyword-only candidate rate;
- B2/B3 identical Top-10 rate;
- B3 improved/unchanged/regressed question IDs;
- latency p50/p95 and provider call accounting.

Accept only if B3 File Recall@5 or MRR is higher than B2 vector-only, B3 File
Recall@10 is not below B2's current 0.9815, and B2/B3 are not identical for all
36 questions. Recall@5 is the stricter primary shortlist metric; Recall@10 is
reported as broad candidate coverage. A changed ranking alone is not called an
improvement.

### Task 7: Independent acceptance review

**Files:**
- Review all modified files and new Task 6 artifacts

- [ ] **Step 1: Dispatch an implementation reviewer subagent**

The reviewer must not have implemented the change. It checks parser
generalizability, SQL/project isolation, deterministic ranking, exact-query
regressions, unchanged 0.7/0.3 weights, and absence of Pilot/gold vocabulary.

- [ ] **Step 2: Dispatch a result reviewer subagent**

The reviewer independently recomputes contribution and Recall metrics from raw
artifacts and checks that the report does not claim hybrid superiority unless
the measured comparison supports it.

- [ ] **Step 3: Fix and re-review every Critical or Major finding**

Do not complete the task while either independent reviewer reports a Critical
or Major issue.

- [ ] **Step 4: Stop before weight experiments**

Report the lexical-repair checkpoint to the user. The next plan, after user
confirmation, will evaluate 0.7/0.3, 0.5/0.5, 0.3/0.7, and RRF using the frozen
repaired keyword branch.

No commit or push is performed unless the user explicitly requests it.
