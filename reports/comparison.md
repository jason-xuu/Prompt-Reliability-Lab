# Prompt Template Comparison Report

**Versions compared:** V1, V2, V3
**Model:** llama3.1:8b

---

## Overall Scores

| Version | Overall | Normal | Ambiguous | Adversarial |
|---------|---------|--------|-----------|-------------|
| V1 | 70.8% | 60.0% | 86.0% | 62.0% |
| V2 | 85.9% | 91.4% | 89.3% | 68.0% |
| V3 | 91.2% | 90.6% | 96.5% | 81.6% |

## Per-Metric Comparison

| Metric | V1 | V2 | V3 | Δ (first→last) |
|--------|-------|-------|-------|---------|
| consistency | 100.0% | 100.0% | 100.0% | +0.0% |
| geometry_validity | 50.0% | 82.6% | 82.6% | +32.6% |
| hallucination_rate | 100.0% | 86.2% | 91.7% | -8.3% |
| instruction_adherence | 18.0% | 68.8% | 86.6% | +68.6% |
| recovery_behavior | 86.0% | 91.8% | 95.0% | +9.0% |

## V2 → V3 instruction adherence (portfolio acceptance)

Same model and run settings must be used for V2 and V3 when interpreting this row.

| Version | Instruction adherence |
|---------|-------------------------|
| V2 | 68.8% |
| V3 | 86.6% |

**Absolute change (V2 → V3):** +17.8 percentage points.

**Relative change:** +25.9% vs V2 baseline.

**Meets a relative reading of the plan:** instruction adherence improved by **25.9%** relative to V2 (≥20% relative improvement). Absolute gain is **+17.8 percentage points** (below 20 pp if that was the intent).


## Improvement Summary

**Overall improvement (v1 → v3):** 📈 +20.4 percentage points

### Key Changes Between Versions

| Version | Key Additions |
|---------|--------------|
| V1 (Baseline) | Minimal instructions, no schema, no error handling |
| V2 (Structured) | Explicit JSON schema, operation type catalog, basic rules |
| V3 (Chain-of-Thought) | Reasoning steps, self-validation, exhaustive rules, worked examples, confidence scoring |

### Failure Reduction

| Failure Type | V1 | V3 | Change |
|-------------|---|---|--------|
| accepted_invalid | 0 | 3 | ❌ +3 |
| hallucinated_extra | 0 | 7 | ❌ +7 |
| invalid_range | 0 | 2 | ❌ +2 |
| missing_params | 2 | 8 | ❌ +6 |
| no_explanation | 10 | 2 | ✅ -8 |
| refused_valid | 0 | 1 | ❌ +1 |
| schema_violation | 0 | 1 | ❌ +1 |
| wrong_operation | 50 | 5 | ✅ -45 |
