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

- Python ≥ 3.10
- OpenAI API key

### Setup

```bash
# Clone and enter project
cd prompt-reliability-lab

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Configure API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Run Evaluation

```bash
# Evaluate a single template
python evaluate.py --template v3

# Compare all three templates (recommended)
python evaluate.py --template v1 v2 v3

# Quick single-run check (no consistency measurement)
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
│       └── openai_adapter.py   # OpenAI API wrapper with retry
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

## Failure Taxonomy

The evaluator automatically classifies failures into 9 types:

| Type | Description |
|------|-------------|
| `missing_params` | Required parameters absent |
| `wrong_operation` | Wrong operation type |
| `hallucinated_extra` | Unrequested operations added |
| `invalid_range` | Values outside valid range |
| `refused_valid` | Valid request incorrectly refused |
| `accepted_invalid` | Invalid request incorrectly accepted |
| `inconsistent_output` | Different results on repeated runs |
| `no_explanation` | Missing assumption/error explanation |
| `schema_violation` | Output doesn't match JSON schema |

## Configuration

All settings are in `.env`:

```env
OPENAI_API_KEY=sk-...          # Required
OPENAI_MODEL=gpt-4o            # Model to test
OPENAI_TEMPERATURE=0.2         # Lower = more deterministic
CONSISTENCY_RUNS=3             # Runs per prompt for consistency
MAX_CONCURRENT_REQUESTS=5     # Rate limiting
```

## Known Limitations

1. **API dependency:** Requires valid OpenAI API key and internet access
2. **Cost:** Full evaluation (50 prompts × 3 templates × 3 runs) = ~450 API calls
3. **Latency:** Full run takes 15-30 minutes depending on rate limits
4. **No Anthropic adapter yet:** Currently OpenAI-only (adapter interface exists for extension)
5. **Consistency metric sensitivity:** Low temperature reduces variance but may mask real inconsistencies
6. **Gold expectations are opinionated:** Ambiguous prompt scoring requires judgment calls about "correct" behavior

## Architecture

```
User → evaluate.py (CLI)
         ↓
       Runner (orchestration)
         ↓
       OpenAIAdapter (LLM calls)
         ↓
       Evaluator (scoring)
         ↓
       Metrics (5 metric functions)
         ↓
       Reporter (markdown + terminal output)
```

## Interview Talking Points

- **Problem:** LLM outputs for geometry commands are unreliable without prompt engineering
- **Approach:** Systematic test corpus + measurable metrics + iterative improvement
- **Key insight:** Chain-of-thought self-validation significantly reduces hallucination
- **What failed:** V1 accepted adversarial inputs; V2 was too rigid with ambiguous prompts
- **What I changed:** V3 adds explicit ambiguity handling taxonomy and worked examples
