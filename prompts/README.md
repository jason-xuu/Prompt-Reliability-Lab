# Prompt corpus and gold expectations

This folder holds the **evaluation corpus** and **reference answers** used by `evaluate.py` and `src/runner.py`.

## Files

| File | Role |
|------|------|
| `corpus.csv` | **50 prompts** (IDs `N01`–`N20` normal, `A01`–`A20` ambiguous, `E01`–`E10` adversarial). One row per prompt: `id`, `category`, `difficulty`, `prompt_text`. |
| `gold_expectations.json` | **50 entries** keyed by prompt ID. Each describes expected operation class, parameters, validity, and scoring hints for ambiguous/adversarial cases. |
| `templates/` | **V1** (baseline), **V2** (structured JSON + catalog), **V3** (chain-of-thought + validation). |

## Gold schema (per prompt ID)

Each gold object may include:

- **`operation_class`** / **`operation_type`** — Expected high-level operation.
- **`required_params`** / **`expected_values`** — What a correct geometry response should contain.
- **`constraints`** — e.g. selection required, destructive ops forbidden.
- **`valid_response`** — Whether a successful geometry answer is expected (`true`) or refusal/clarification (`false`).
- **`ambiguous_behavior`** (when applicable) — Expected handling: clarification, defaults with assumptions, etc.
- **`notes`** — Human-readable intent for maintainers and interview discussion.

The evaluator (`src/evaluator.py`) and metrics (`src/metrics.py`) use this file as the single source of truth for automated scoring.

## Category intent

- **Normal** — Clear NL geometry requests with explicit or implied parameters.
- **Ambiguous** — Underspecified language where clarification or stated assumptions is appropriate.
- **Adversarial** — Invalid numbers, contradictions, injection-style text, or missing CAD context; safe refusal or explicit error status is often expected.

For scoring definitions and failure types, see `rubric.md` in the project root.
