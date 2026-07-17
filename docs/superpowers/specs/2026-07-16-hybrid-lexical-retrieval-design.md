# Hybrid Lexical Retrieval Repair Design

Date: 2026-07-16
Status: proposed for implementation

## 1. Problem and evidence

The Stage 2B Pilot showed that B2 vector-only and B3 hybrid retrieval produced
identical Top-10 rankings for all 36 questions. The same degeneration appeared
across A2, A3, and A4. The hybrid pipeline existed structurally, but its keyword
branch made no effective ranking contribution.

The root cause is in `KeywordSearchService`: it applies one substring predicate
to the complete rewritten natural-language query. For example, it searches for
the literal phrase `user login controller HTTP method path`. No indexed entity
contains that complete sentence, while individual terms such as `user` and
`login` do match indexed code entities. This is a lexical query interpretation
failure, not primarily a fusion-weight failure.

## 2. Scope

This stage changes only lexical candidate retrieval used by keyword and hybrid
search. It does not change:

- the 0.7 vector / 0.3 keyword fusion weights;
- query-rewrite prompts or providers;
- vector embeddings or Qdrant indexing;
- graph retrieval, Agent routing, answer generation, or evidence validation;
- frozen Stage 2B raw results.

Fusion-weight experiments are explicitly deferred to the next stage. They will
start only after the repaired keyword branch has demonstrated real candidate
and ranking contribution, so lexical repair and weight effects remain
separately attributable.

## 3. Considered approaches

### 3.1 Selected: code-aware multi-term lexical retrieval

Parse a query into bounded, code-aware terms and rank entities by distinct-term
coverage plus existing field relevance. This keeps the current SQLite source of
truth, fixes both direct keyword and hybrid behavior, and is small enough to
verify thoroughly.

### 3.2 Rejected for this stage: hybrid-only query fan-out

The hybrid service could split a query and call the existing keyword service
once per term. This has a smaller initial blast radius, but leaves direct
keyword search broken for natural language, duplicates aggregation logic, and
causes multiple database round trips.

### 3.3 Deferred: SQLite FTS5/BM25

FTS5 would provide a stronger long-term lexical foundation, but it requires a
new index lifecycle, schema migration, synchronization after scans, and new
operational failure modes. It is outside this focused repair.

## 4. Proposed architecture

### 4.1 Lexical query parser

Add a small retrieval-layer component responsible only for deterministic query
parsing. It uses compiled regular expressions for paths and ASCII compound
boundaries, plus Python's standard-library `unicodedata` categories for full
Unicode identifier continuation characters. It will:

- case-fold and de-duplicate terms;
- preserve structured code tokens such as API paths, filenames, qualified
  names, camelCase identifiers, and snake_case identifiers;
- split ordinary natural-language text into individual terms;
- retain useful identifier components when a compound identifier is split;
- filter a language-level stop-word list, never a repository- or Pilot-specific
  vocabulary;
- enforce a fixed maximum term count to bound SQL size and latency;
- return no terms for an empty or stop-word-only query.

No third-party tokenizer is introduced. A category-aware scanner is required
because Python's built-in `re` `\w` class does not cover every valid combining
mark used by Python, Java, and JavaScript identifiers.

The parser must not contain `RuoYi`, question IDs, gold entities, or special
rules for Pilot concepts such as login, captcha, role, or department.

### 4.2 Keyword candidate retrieval

`KeywordSearchService` will preserve its current exact behavior for a single
structured term or path. For multi-term queries, it will register a
deterministic SQLite lexical-score function on the active connection and issue
one project-scoped SQL query. The score function receives the existing
searchable fields:

- `name`;
- `qualified_name`;
- `metadata_json`;
- `file_path`;
- `content`.

The database query orders by lexical score and entity ID and applies `LIMIT`
before ORM entities are materialized. It must not load every matching entity
and its complete source content into Python for sorting. Stored fields and
query terms are compared after Unicode NFC normalization and case folding.
Project isolation and the existing `PROJECT_NOT_FOUND` behavior remain
unchanged.

### 4.3 Deterministic lexical ranking

Each candidate is scored from:

1. distinct parsed-term coverage;
2. the existing field priority, with name and qualified-name matches ahead of
   file path and content;
3. exact identifier, filename, or API-path matches;
4. deterministic entity-ID tie-breaking.

For multi-term queries, low-information structural terms (`controller`, `api`,
`method`, `path`, `file`, `class`, `endpoint`, `http`, `code`, and `module`)
have weight 0.25; other terms have weight 1.0. They are downweighted rather
than removed. The score is:

`0.6 * matched_weight / total_weight + 0.4 * weighted_field_signal / total_weight`.

A complete structured identifier, filename, or path match has priority over
component fallback. Component matching is used only when the complete value has
no match. Single-term scoring and ordering remain backward compatible.

The score is used only to rank the keyword branch. Hybrid fusion continues to
normalize branch scores and apply the unchanged 0.7/0.3 weights. The first
implementation must not introduce corpus-specific tuning or claim BM25.

## 5. Data flow

1. Query rewriting produces the same effective query as today.
2. Vector retrieval embeds and searches that effective query unchanged.
3. The lexical parser converts the effective query into bounded search terms.
4. Keyword retrieval obtains and ranks candidates using those terms.
5. Existing hybrid fusion deduplicates vector and keyword candidates and applies
   0.7/0.3 normalization.
6. Existing API and service response contracts remain unchanged.

## 6. Error handling and compatibility

- Empty and stop-word-only queries return no keyword hits without broadening to
  a match-all query.
- A keyword failure retains the existing vector fallback behavior.
- A vector failure retains the existing keyword fallback behavior.
- A missing project remains a domain error and must not be hidden by fallback.
- Existing exact symbol, filename, wildcard-literal, and API-path searches must
  retain deterministic results.
- No new external dependency or database migration is introduced.

## 7. Test strategy

Implementation follows red-green-refactor. Tests are written and observed
failing before production changes.

Required test groups:

- parser tests for natural language, paths, camelCase, snake_case, duplicates,
  stop words, empty input, Unicode, and the maximum-term bound;
- keyword integration tests proving a sentence with no whole-phrase match can
  retrieve entities through multiple relevant terms;
- ranking tests proving generic structural-word decoys do not outrank entities
  matching the domain-bearing terms;
- real SQLite tests for NFC/casefold matching and SQL-side ordering/limits;
- regression tests for exact identifiers, API paths, SQL wildcard escaping,
  project isolation, limits, and deterministic ties;
- hybrid tests proving the keyword branch contributes candidates or reranking
  while the fusion weights remain exactly 0.7/0.3;
- full backend and evaluation regression suites.

## 8. Evaluation and acceptance gates

New evaluation artifacts must use a new run/output identity and must not
overwrite the frozen Stage 2B raw files.

The lexical repair is accepted only if:

1. the rewritten-query keyword branch is no longer zero-hit for all 36 Pilot
   questions;
2. B3 hybrid and B2 vector are no longer identical for all 36 Top-10 rankings;
3. B3 File Recall@5 or MRR is higher than B2 vector-only, while B3 File
   Recall@10 is not lower than the current B2 value of 0.9815;
4. exact identifier and API-path regression tests pass;
5. no Pilot-specific vocabulary or gold data enters production retrieval;
6. raw contribution diagnostics record keyword hit counts, overlap, and ranking
   changes so the result is explainable in an interview;
7. an independent review finds no Critical or Major issue in the implementation
   or evaluation claim.

The initial post-fix comparison keeps the fusion weights fixed. A later,
separate experiment will compare weight settings such as 0.7/0.3, 0.5/0.5,
0.3/0.7, and RRF using the repaired lexical branch.

## 9. Interview-safe claim boundary

If the gates pass, the project may claim that a code-aware lexical parser made
the keyword branch operational and that the repaired hybrid pipeline was
measured against vector-only, keyword-only, and grep baselines. It may report
the observed Recall@5, Recall@10, MRR, and contribution diagnostics. Recall@10
is broad candidate coverage; Recall@5 is the stricter primary metric for the
shortlist presented to downstream answer generation.

It must not claim that hybrid retrieval is universally better than vector
retrieval, that the selected weights are optimal, or that a single-repository
Pilot establishes cross-repository generalization.
