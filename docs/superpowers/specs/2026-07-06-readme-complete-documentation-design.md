# Complete README Documentation Design

## Goal

Rewrite the root `README.md` as a complete, English-language project document
that serves both portfolio readers and developers who want to run, inspect, or
extend ResearchCode-Agent.

## Documentation Principles

- Describe only behavior implemented on the current `main` branch.
- Tie technical claims to code, configuration, APIs, or automated tests.
- Separate implemented capabilities from future roadmap items.
- Explain important design choices and limitations without overstating the
  system's autonomy or supported analysis.
- Keep the project overview concise enough for recruiters while providing
  detailed setup and reference material for developers.

## Accuracy Boundaries

The README will explicitly state that:

- the Agent planner deterministically routes each question to one of
  `CODE_QA`, `TRACE_CHAIN`, or `CHANGE_PLAN`;
- the current system does not use an LLM to autonomously decompose tasks or
  choose tools;
- `ToolRegistry` exposes named service callables internally, but is not an LLM
  function-calling loop;
- the parsed entity types are Java classes and methods, backend APIs, frontend
  API calls, and Python classes and functions;
- the persisted relation types are `CONTAINS`, `DEFINES_API`, `REQUESTS_API`,
  and `CALLS_METHOD`;
- retrieval indexes parsed code entities rather than arbitrary project
  documentation;
- static graph evidence is not proof of runtime behavior;
- no repository-scale performance claim will be made without benchmark data.

## Proposed README Structure

1. Project title and concise value proposition
2. Key capabilities
3. End-to-end architecture and data flow
4. Technology stack
5. Supported source languages and scanned file types
6. Parsed entities and relation model
7. Indexing, retrieval, and GraphRAG behavior
8. Agent planning, execution, conversation persistence, and grounding
9. Backend and frontend structure
10. Prerequisites and configuration
11. Installation and startup from the repository root
12. Project registration, scanning, and vector-index workflow
13. Frontend routes
14. Complete API reference with representative requests
15. Offline scripts and inspection utilities
16. Automated testing and verification
17. Reliability safeguards and failure behavior
18. Known limitations
19. Explicitly labeled roadmap

## Content Sources

The rewrite will use the following as sources of truth:

- backend API routers and Pydantic schemas for endpoint contracts;
- parser types and parser implementations for supported entities and
  relations;
- retrieval, graph, RAG, and Agent services for runtime behavior;
- `.env.example` and settings for configuration;
- frontend router and views for user-facing routes;
- unit, integration, and acceptance tests for verified behavior;
- existing root and backend README files for useful commands that remain
  accurate.

## Validation

Because this is a documentation-only change, validation will focus on:

- checking every command and path against the current repository layout;
- checking endpoint names and payload fields against router and schema code;
- checking all capability claims against implementations or tests;
- scanning for stale `.worktrees` paths and unsupported claims;
- reviewing Markdown headings, code fences, links, and formatting;
- running a lightweight repository diff and status review before completion.

No real LLM calls, embedding-model downloads, browser inspection, or other
high-token verification will be used.
