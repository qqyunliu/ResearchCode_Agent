# ResearchCode-Agent Evaluation System

This directory contains the long-term evaluation framework for ResearchCode-Agent.
It is designed to produce reproducible, evidence-based answers to the
following questions:

1. Why is this project needed instead of grep, IDE search, or plain keyword search?
2. Does vector retrieval outperform keyword retrieval?
3. Does Hybrid Search outperform either keyword or vector alone?
4. Does GraphRAG improve call-chain tracing?
5. Does the unified Agent workflow add measurable value?
6. Do citations and uncertainty mechanisms reduce unsupported answers?
7. Where does the system fail (languages, frameworks, question types, repo sizes)?
8. Are the complex components worth their cost, latency, and maintenance?

## Directory Layout

```
evaluation/
  README.md            # This file
  SPEC.md              # Full evaluation specification
  repos/
    manifest.yaml      # Registered repositories with fixed commit SHAs
  schema/
    evaluation_case.schema.json  # JSON Schema for evaluation cases
  datasets/
    pilot.jsonl         # Pilot dataset (30-50 questions, 1 repo)
    development.jsonl   # Development split (multi-repo)
    validation.jsonl    # Validation split (held-out repo)
    holdout.jsonl       # Holdout split (never used for tuning)
  annotations/
    proposed/           # Machine-proposed annotations
    reviewed/           # Adversarial-reviewed annotations
    disagreements/      # Unresolved disagreements between agents
  scripts/              # Utility scripts (validation, data generation)
  runners/              # Baseline and evaluation runners
  reports/
    pilot-report.md     # Pilot experiment results
    benchmark-report.md # Full benchmark results
    failure-catalog.md  # Cataloged failure cases
    interview-evidence.md  # Evidence for interview questions
  results/
    raw/                # Raw model outputs (never modified)
    metrics/            # Computed metrics (JSON)
  workspaces/
    .gitkeep            # Cloned repos go here (not committed)
```

## Principles

- The evaluation finds problems, it does not prove the system is good.
- Gold labels are never adjusted to match system output.
- Question generation and evidence annotation are performed by separate agents.
- All adversarial review disagreements are preserved.
- Negative results and failure samples are retained and reported.
- Machine-verified data is clearly labeled; it is not called "human gold standard."
- No paid API is called without explicit user authorization.

## Planned Commands (not yet implemented)

The following commands will be available once the evaluation scripts are created
in Stage 2A. They are listed here as a design target, not as runnable instructions.

```bash
# 1. Validate dataset schema and semantic constraints
cd evaluation
python scripts/validate_dataset.py datasets/pilot.jsonl

# 2. Run offline baselines (no LLM needed)
python runners/baseline_rg.py --dataset datasets/pilot.jsonl --repo workspaces/ruoyi-vue
python runners/baseline_keyword.py --dataset datasets/pilot.jsonl --db runtime/pilot/rca_eval.db

# 3. Compute retrieval metrics
python scripts/compute_retrieval_metrics.py --predictions results/raw/b1_keyword.jsonl --gold datasets/pilot.jsonl

# 4. Run full benchmark (requires running backend + API keys — NOT YET AUTHORIZED)
# python runners/benchmark.py --dataset datasets/pilot.jsonl --output results/
```

## Status

- Stage 0 (Project Investigation): Complete
- Stage 1 (Evaluation Design): In progress (this directory)
- Stage 2 (Pilot Dataset): Pending user approval
