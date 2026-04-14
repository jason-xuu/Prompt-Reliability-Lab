"""
Metrics computation for prompt evaluation.

Computes five key metrics against gold expectations:
  1. Instruction adherence  — does the output match the requested operation class?
  2. Geometry validity       — are all required params present and within range?
  3. Hallucination rate      — does the output contain unrequested operations?
  4. Consistency             — repeated runs produce the same structural output?
  5. Recovery behavior       — malformed prompts handled gracefully?

Each metric returns a 0.0–1.0 score and a human-readable explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Result Container ──────────────────────────────────────────────────────

@dataclass
class MetricResult:
    """Result of a single metric evaluation."""

    name: str
    score: float  # 0.0 – 1.0
    explanation: str
    details: dict[str, Any] = field(default_factory=dict)


# ── 1. Instruction Adherence ─────────────────────────────────────────────

def instruction_adherence(
    response: dict[str, Any],
    gold: dict[str, Any],
) -> MetricResult:
    """
    Check whether the model's output matches the expected operation class.

    For normal prompts: does the output contain operations of the correct type?
    For ambiguous prompts: does it set clarification_needed or provide reasonable defaults?
    For adversarial prompts: does it refuse / flag the error correctly?
    """
    gold_class = gold.get("operation_class", "")
    expected_behavior = gold.get("expected_behavior", "")
    status = response.get("status", "")

    # ── Invalid / adversarial prompts ──
    if gold_class == "invalid":
        if expected_behavior == "reject_with_explanation" and status == "error":
            return MetricResult("instruction_adherence", 1.0, "Correctly rejected invalid input")
        if expected_behavior == "reject_destructive" and status == "error":
            return MetricResult("instruction_adherence", 1.0, "Correctly refused destructive operation")
        if expected_behavior == "reject_injection" and status == "error":
            return MetricResult("instruction_adherence", 1.0, "Correctly refused prompt injection")
        if expected_behavior == "warn_and_proceed_or_reject" and status in ("error", "success"):
            warnings = response.get("warnings", [])
            if warnings:
                return MetricResult("instruction_adherence", 0.8, "Proceeded with warning (acceptable)")
            if status == "error":
                return MetricResult("instruction_adherence", 1.0, "Correctly rejected")
        if expected_behavior == "resolve_or_reject" and status in ("error", "clarification_needed"):
            return MetricResult("instruction_adherence", 1.0, "Correctly handled conflicting params")
        if expected_behavior == "warn_no_selection" and status in ("error", "clarification_needed"):
            return MetricResult("instruction_adherence", 1.0, "Correctly flagged missing selection")
        if expected_behavior == "request_clarification" and status == "clarification_needed":
            return MetricResult("instruction_adherence", 1.0, "Correctly requested clarification")
        # If it should have errored but didn't
        if status == "success":
            return MetricResult("instruction_adherence", 0.0, "Should have rejected but accepted")
        return MetricResult("instruction_adherence", 0.3, f"Partial handling: status={status}")

    # ── Ambiguous prompts ──
    if gold_class == "ambiguous":
        if expected_behavior == "request_clarification" and status == "clarification_needed":
            return MetricResult("instruction_adherence", 1.0, "Correctly requested clarification")
        if expected_behavior in ("request_clarification_or_default", "infer_and_explain"):
            if status in ("clarification_needed", "success"):
                assumptions = response.get("assumptions", [])
                if status == "success" and assumptions:
                    return MetricResult("instruction_adherence", 1.0, "Provided defaults with assumptions")
                if status == "success" and not assumptions:
                    return MetricResult("instruction_adherence", 0.5, "Provided defaults without explaining assumptions")
                if status == "clarification_needed":
                    return MetricResult("instruction_adherence", 0.8, "Requested clarification (acceptable)")
            return MetricResult("instruction_adherence", 0.3, f"Unexpected handling: status={status}")
        if expected_behavior == "request_clarification_or_refuse":
            if status in ("clarification_needed", "error"):
                return MetricResult("instruction_adherence", 1.0, "Correctly flagged or refused")
        return MetricResult("instruction_adherence", 0.3, f"Unhandled ambiguous behavior: {expected_behavior}")

    # ── Normal prompts ──
    if status != "success":
        return MetricResult(
            "instruction_adherence", 0.0,
            f"Expected successful operation but got status='{status}'"
        )

    operations = response.get("operations", [])
    if not operations:
        return MetricResult("instruction_adherence", 0.0, "No operations in response")

    # Check if any operation matches the expected class
    gold_type = gold.get("operation_type", "")
    if gold_class in ("multi_step", "composite"):
        expected_steps = gold.get("steps", [])
        if len(operations) >= len(expected_steps):
            return MetricResult("instruction_adherence", 1.0, "Multi-step operations present")
        return MetricResult(
            "instruction_adherence",
            len(operations) / max(len(expected_steps), 1),
            f"Expected {len(expected_steps)} steps, got {len(operations)}",
        )

    matched = any(
        op.get("type") == gold_class or op.get("subtype") == gold_type
        for op in operations
    )
    if matched:
        return MetricResult("instruction_adherence", 1.0, "Correct operation class")

    # Partial credit: right category, wrong specific type
    partial = any(
        _same_category(op.get("type", ""), gold_class) for op in operations
    )
    if partial:
        return MetricResult("instruction_adherence", 0.5, "Similar category but wrong specific operation")

    return MetricResult(
        "instruction_adherence", 0.0,
        f"Expected {gold_class}/{gold_type}, got {[op.get('type') for op in operations]}",
    )


# ── 2. Geometry Validity ─────────────────────────────────────────────────

def geometry_validity(
    response: dict[str, Any],
    gold: dict[str, Any],
) -> MetricResult:
    """
    Check that all required parameters are present, correctly typed,
    and within valid ranges.
    """
    gold_class = gold.get("operation_class", "")

    # Non-geometry prompts (ambiguous / invalid) — validity doesn't apply in the same way
    if gold_class in ("ambiguous", "invalid"):
        status = response.get("status", "")
        if gold_class == "invalid" and status == "error":
            return MetricResult("geometry_validity", 1.0, "Correctly identified invalid geometry")
        if gold_class == "ambiguous":
            return MetricResult("geometry_validity", 1.0, "N/A for ambiguous prompts (scored via adherence)")
        return MetricResult("geometry_validity", 0.5, "Partial validity assessment for edge case")

    operations = response.get("operations", [])
    if not operations:
        return MetricResult("geometry_validity", 0.0, "No operations to validate")

    required_params = gold.get("required_params", [])
    expected_values = gold.get("expected_values", {})
    issues: list[str] = []
    checks_passed = 0
    total_checks = 0

    # For multi-step, check each step
    if gold_class in ("multi_step", "composite"):
        gold_steps = gold.get("steps", [])
        for i, gs in enumerate(gold_steps):
            step_params = gs.get("params", {})
            if i < len(operations):
                op = operations[i]
                for pk, pv in step_params.items():
                    total_checks += 1
                    op_params = op.get("params", {})
                    if pk in op_params:
                        if _values_close(op_params[pk], pv):
                            checks_passed += 1
                        else:
                            issues.append(f"Step {i}: {pk} expected {pv}, got {op_params[pk]}")
                    else:
                        issues.append(f"Step {i}: missing param '{pk}'")
            else:
                total_checks += len(step_params)
                issues.append(f"Step {i}: operation missing entirely")
    else:
        # Single operation — check required params
        op = operations[0]
        op_params = op.get("params", {})
        for rp in required_params:
            total_checks += 1
            if rp in op_params:
                checks_passed += 1
            else:
                issues.append(f"Missing required param: '{rp}'")

        # Check expected values
        for ek, ev in expected_values.items():
            total_checks += 1
            if ek in op_params:
                if _values_close(op_params[ek], ev):
                    checks_passed += 1
                else:
                    issues.append(f"Param '{ek}': expected {ev}, got {op_params[ek]}")
            elif ek in required_params:
                pass  # Already counted as missing
            else:
                total_checks -= 1  # Optional param, don't penalize

        # Check for negative / zero dimensions
        for pk, pv in op_params.items():
            if isinstance(pv, (int, float)) and pk in ("width", "height", "depth", "radius"):
                total_checks += 1
                if pv > 0:
                    checks_passed += 1
                else:
                    issues.append(f"Invalid {pk}: {pv} (must be > 0)")

    if total_checks == 0:
        return MetricResult("geometry_validity", 1.0, "No specific params to validate")

    score = checks_passed / total_checks
    explanation = f"{checks_passed}/{total_checks} checks passed"
    if issues:
        explanation += ". Issues: " + "; ".join(issues[:5])

    return MetricResult("geometry_validity", round(score, 3), explanation, {"issues": issues})


# ── 3. Hallucination Rate ────────────────────────────────────────────────

def hallucination_rate(
    response: dict[str, Any],
    gold: dict[str, Any],
) -> MetricResult:
    """
    Check if the output includes operations that weren't requested.
    Score: 1.0 = no hallucinations, 0.0 = everything is hallucinated.
    """
    gold_class = gold.get("operation_class", "")

    if gold_class in ("ambiguous", "invalid"):
        # For ambiguous: if the model generates ops, check they're reasonable
        operations = response.get("operations", [])
        if gold_class == "invalid" and operations:
            return MetricResult("hallucination_rate", 0.0, "Generated operations for invalid input")
        return MetricResult("hallucination_rate", 1.0, "N/A for this category")

    operations = response.get("operations", [])
    if not operations:
        return MetricResult("hallucination_rate", 1.0, "No operations (no hallucination possible)")

    # Determine how many operations were expected
    if gold_class in ("multi_step", "composite"):
        expected_count = len(gold.get("steps", []))
    else:
        expected_count = 1

    extra = max(0, len(operations) - expected_count)
    if extra == 0:
        return MetricResult("hallucination_rate", 1.0, "No extra operations")

    # Check if extra operations are related (e.g., implied intermediate steps)
    hallucination_score = 1.0 - (extra / (len(operations)))
    return MetricResult(
        "hallucination_rate",
        round(max(0, hallucination_score), 3),
        f"{extra} unrequested operation(s) out of {len(operations)} total",
        {"expected_count": expected_count, "actual_count": len(operations)},
    )


# ── 4. Consistency ───────────────────────────────────────────────────────

def consistency(
    responses: list[dict[str, Any]],
    gold: dict[str, Any],
) -> MetricResult:
    """
    Given multiple responses for the same prompt, measure structural consistency.
    Checks: same status, same operation types, same param values.
    """
    if len(responses) < 2:
        return MetricResult("consistency", 1.0, "Only one response (trivially consistent)")

    checks: list[bool] = []

    # Check status consistency
    statuses = [r.get("status", "") for r in responses]
    checks.append(len(set(statuses)) == 1)

    # Check operation count consistency
    op_counts = [len(r.get("operations", [])) for r in responses]
    checks.append(len(set(op_counts)) == 1)

    # Check operation types consistency
    op_types = []
    for r in responses:
        types = tuple(
            (op.get("type", ""), op.get("subtype", ""))
            for op in r.get("operations", [])
        )
        op_types.append(types)
    checks.append(len(set(op_types)) == 1)

    # Check key parameter consistency (first operation only)
    if all(r.get("operations") for r in responses):
        first_ops = [r["operations"][0] for r in responses]
        param_keys = set()
        for op in first_ops:
            param_keys.update(op.get("params", {}).keys())
        for pk in param_keys:
            vals = [op.get("params", {}).get(pk) for op in first_ops]
            # Compare with tolerance for floats
            if all(isinstance(v, (int, float)) for v in vals if v is not None):
                numeric_vals = [v for v in vals if v is not None]
                if numeric_vals:
                    checks.append(max(numeric_vals) - min(numeric_vals) < 0.01)
            else:
                checks.append(len(set(str(v) for v in vals)) == 1)

    passed = sum(checks)
    total = len(checks)
    score = passed / total if total > 0 else 1.0

    return MetricResult(
        "consistency",
        round(score, 3),
        f"{passed}/{total} consistency checks passed",
        {"statuses": statuses, "op_counts": op_counts},
    )


# ── 5. Recovery Behavior ─────────────────────────────────────────────────

def recovery_behavior(
    response: dict[str, Any],
    gold: dict[str, Any],
) -> MetricResult:
    """
    For malformed / adversarial prompts, check that the model recovers
    gracefully: refuses clearly, provides warnings, doesn't crash.
    """
    gold_class = gold.get("operation_class", "")
    expected_behavior = gold.get("expected_behavior", "")
    error_type = gold.get("error_type", "")

    # Only applies to invalid / adversarial prompts
    if gold_class != "invalid":
        return MetricResult("recovery_behavior", 1.0, "N/A for non-adversarial prompts")

    status = response.get("status", "")
    warnings = response.get("warnings", [])
    clarification = response.get("clarification_request")

    score = 0.0
    reasons: list[str] = []

    # Did it detect the problem?
    if status in ("error", "clarification_needed"):
        score += 0.4
        reasons.append("Detected the issue")
    else:
        reasons.append("Failed to detect the issue")

    # Did it explain the problem?
    if warnings:
        score += 0.3
        reasons.append("Provided warning/explanation")
    elif clarification:
        score += 0.2
        reasons.append("Requested clarification")
    else:
        reasons.append("No explanation provided")

    # Did it avoid generating bad geometry?
    operations = response.get("operations", [])
    if not operations or all(op.get("type") != "create_primitive" for op in operations):
        score += 0.3
        reasons.append("Did not generate invalid geometry")
    else:
        reasons.append("Generated geometry despite error")

    return MetricResult(
        "recovery_behavior",
        round(min(score, 1.0), 3),
        "; ".join(reasons),
        {"error_type": error_type, "expected_behavior": expected_behavior},
    )


# ── Helpers ───────────────────────────────────────────────────────────────

def _values_close(a: Any, b: Any, tol: float = 0.01) -> bool:
    """Compare two values with tolerance for floats."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < tol
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_values_close(x, y, tol) for x, y in zip(a, b))
    return str(a) == str(b)


def _same_category(op_type: str, gold_class: str) -> bool:
    """Check if an operation type belongs to the same broad category."""
    categories = {
        "create_primitive": {"create_primitive", "create_surface", "create_extrusion"},
        "create_surface": {"create_primitive", "create_surface", "create_extrusion"},
        "create_extrusion": {"create_primitive", "create_surface", "create_extrusion"},
        "transform": {"transform"},
        "pattern": {"pattern"},
    }
    return op_type in categories.get(gold_class, set())
