# Prompt Reliability Lab

> A rigorous evaluation harness for testing and improving LLM prompt templates used in geometry command generation for CAD systems (Rhino/Grasshopper).

## Overview

This project demonstrates disciplined prompt engineering methodology:

1. **Define a test corpus** — 50 prompts across 3 categories (normal, ambiguous, adversarial)
2. **Establish gold expectations** — expected operation types, parameters, and behaviors
3. **Iterate on prompt templates** — V1 (baseline) → V2 (structured) → V3 (chain-of-thought)
4. **Measure improvement** — 5 metrics scored automatically with failure taxonomy
5. **Report findings** — Quantified before/after comparison with actionable recommendations

## Quick Start

### Prerequisites

- Python ≥ 3.10 (3.9 may work but is not targeted)
- One LLM backend: **Gemini** (API key), **OpenAI** (API key), or **Ollama** (local, no key)

### Setup

```bash
# Clone and enter project
cd prompt-reliability-lab

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Configure provider and keys (see .env.example)
cp .env.example .env
# Edit .env: set LLM_PROVIDER and model / API key as appropriate
```

### Run Evaluation

```bash
# Evaluate a single template
python evaluate.py --template v3

# Full portfolio run: all templates + reports/comparison.md (recommended before sign-off)
python evaluate.py --template v1 v2 v3

# Faster sign-off run (same corpus; consistency metric is single-run only)
python evaluate.py --template v1 v2 v3 --runs 1

# Quick single-template check
python evaluate.py --template v3 --runs 1

# Verbose mode for debugging
python evaluate.py --template v3 --runs 1 --verbose
```

### Run Tests

```bash
pytest tests/ -v
```

## Project Structure

```
prompt-reliability-lab/
├── evaluate.py                 # CLI entry point
├── prompts/
│   ├── README.md               # Corpus + gold documentation
│   ├── corpus.csv              # 50-prompt test corpus
│   ├── gold_expectations.json  # Expected outputs per prompt
│   └── templates/
│       ├── v1_baseline.txt     # Naive prompt (intentionally weak)
│       ├── v2_structured.txt   # JSON schema + operation catalog
│       └── v3_cot.txt          # Chain-of-thought + self-validation
├── src/
│   ├── config.py               # Configuration management
│   ├── runner.py               # Orchestrates evaluation runs
│   ├── evaluator.py            # Scores responses against expectations
│   ├── metrics.py              # 5 metric implementations
│   ├── reporter.py             # Markdown + terminal report generation
│   └── models/
│       ├── gemini_adapter.py   # Google Gemini
│       ├── openai_adapter.py   # OpenAI
│       └── ollama_adapter.py   # Local Ollama (OpenAI-compatible API)
├── reports/                    # Generated evaluation reports
├── rubric.md                   # Scoring criteria documentation
├── tests/                      # pytest test suite
└── pyproject.toml              # Dependencies
```

## Metrics

| Metric | What it Measures | Why it Matters |
|--------|-----------------|----------------|
| **Instruction Adherence** | Does output match the requested operation? | Core correctness |
| **Geometry Validity** | Are parameters complete and valid? | Prevents broken geometry |
| **Hallucination Rate** | Any unrequested operations in output? | Safety — no surprise geometry |
| **Consistency** | Same prompt → same output across runs? | Reliability |
| **Recovery Behavior** | Graceful handling of bad input? | Robustness |

## Prompt Template Evolution

### V1 — Baseline
- Minimal instructions ("output a JSON object")
- No schema definition
- No error handling guidance
- **Expected:** Low adherence, high hallucination

### V2 — Structured
- Explicit JSON output schema with required fields
- Full operation type catalog with parameter specs
- Basic validation rules (positive dimensions, no delete)
- **Expected:** Major adherence improvement, reduced schema violations

### V3 — Chain-of-Thought
- 6-step internal reasoning process before generating output
- Self-validation checklist
- Detailed parameter tables with constraints
- Exhaustive validation rules with examples
- Ambiguity handling taxonomy
- Confidence scoring
- **Expected:** Best overall performance, especially on edge cases

## Failure taxonomy and fix strategies

The evaluator classifies failures into discrete types. **What to do about each type** is documented in:

- **`rubric.md`** — table of failure types with **typical fix** strategies
- **`reports/v*_report.md`** — per-run table with **Fix Strategy** column (same mapping as the rubric)

Types include: `missing_params`, `wrong_operation`, `hallucinated_extra`, `invalid_range`, `refused_valid`, `accepted_invalid`, `inconsistent_output`, `no_explanation`, `schema_violation`.

## Configuration

All settings are in `.env` (see `.env.example`). Typical variables:

- **`LLM_PROVIDER`** — `gemini` | `openai` | `ollama`
- **`LLM_MODEL`** — provider-specific model id
- **`GEMINI_API_KEY`** / **`OPENAI_API_KEY`** — omit for Ollama
- **`LLM_TEMPERATURE`** — lower is more deterministic
- **`CONSISTENCY_RUNS`** — repeated generations per prompt for the consistency metric
- **`MAX_CONCURRENT_REQUESTS`** — batch size for cloud providers

## Known limitations

1. **Provider dependency:** Cloud modes need network and valid keys; Ollama needs a running local server.
2. **Cost / time:** Full run is **50 × templates × `CONSISTENCY_RUNS`** generations (e.g. 450 calls for three templates and three runs). Local Ollama avoids API cost but is still CPU/GPU bound.
3. **Consistency metric:** With `--runs 1`, the consistency score reflects a single sample per prompt.
4. **Gold expectations are opinionated:** Ambiguous prompts require judgment calls; see `prompts/README.md` and `rubric.md`.

## Architecture

```
User → evaluate.py (CLI)
         ↓
       Runner (orchestration)
         ↓
       GeminiAdapter / OpenAIAdapter / OllamaAdapter
         ↓
       Evaluator (scoring)
         ↓
       Metrics (5 metric functions)
         ↓
       Reporter (markdown + terminal output)
```

## Portfolio acceptance (KPF implementation plan — Project 1)

Use this checklist before treating Prompt Reliability Lab as **complete**:

| Criterion | Where it is satisfied |
|-----------|------------------------|
| **50 prompts + gold** documented | `prompts/corpus.csv`, `prompts/gold_expectations.json`, **`prompts/README.md`** |
| **Three templates + rationale** | **Prompt Template Evolution** (below) + files in `prompts/templates/` |
| **Structured report with all 5 metrics** | `Reporter.save_report` → `reports/v*_report.md` |
| **V2→V3 “≥20%” on instruction adherence** (same model/settings) | **`reports/comparison.md`** — reports **absolute (pp)** and **relative (%)** gain; `implementation_plan.md` wording matches **relative** improvement on this run |
| **Failure taxonomy + fix strategies** | **`rubric.md`** + per-report tables in `reports/v*_report.md` |
| **AI vs deterministic recommendation** | Final section of each **`reports/v*_report.md`** |

**Command to regenerate all evidence:** `python evaluate.py --template v1 v2 v3` (add `--runs 1` for a faster pass at the cost of weaker consistency measurement).

## Interview Talking Points

- **Problem:** LLM outputs for geometry commands are unreliable without prompt engineering
- **Approach:** Systematic test corpus + measurable metrics + iterative improvement
- **Key insight:** Chain-of-thought self-validation significantly reduces hallucination
- **What failed:** V1 accepted adversarial inputs; V2 was too rigid with ambiguous prompts
- **What I changed:** V3 adds explicit ambiguity handling taxonomy and worked examples
