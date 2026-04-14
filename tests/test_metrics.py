"""
Tests for the metrics module.

Validates all 5 metric functions against known input/output pairs
covering normal, ambiguous, and adversarial cases.
"""

import pytest
from src.metrics import (
    instruction_adherence,
    geometry_validity,
    hallucination_rate,
    consistency,
    recovery_behavior,
    MetricResult,
)


# ── Instruction Adherence ─────────────────────────────────────────────────

class TestInstructionAdherence:
    """Tests for instruction_adherence metric."""

    def test_normal_correct_match(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "subtype": "box", "params": {}}],
        }
        gold = {"operation_class": "create_primitive", "operation_type": "box"}
        result = instruction_adherence(response, gold)
        assert result.score == 1.0

    def test_normal_wrong_type(self):
        response = {
            "status": "success",
            "operations": [{"type": "transform", "subtype": "move", "params": {}}],
        }
        gold = {"operation_class": "create_primitive", "operation_type": "box"}
        result = instruction_adherence(response, gold)
        assert result.score == 0.0

    def test_normal_similar_category(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_surface", "subtype": "rectangle", "params": {}}],
        }
        gold = {"operation_class": "create_primitive", "operation_type": "box"}
        result = instruction_adherence(response, gold)
        assert result.score == 0.5

    def test_normal_error_status(self):
        response = {"status": "error", "operations": []}
        gold = {"operation_class": "create_primitive", "operation_type": "box"}
        result = instruction_adherence(response, gold)
        assert result.score == 0.0

    def test_multi_step_complete(self):
        response = {
            "status": "success",
            "operations": [
                {"type": "create_primitive", "params": {}},
                {"type": "transform", "params": {}},
            ],
        }
        gold = {
            "operation_class": "multi_step",
            "steps": [
                {"operation_type": "create_primitive"},
                {"operation_type": "transform"},
            ],
        }
        result = instruction_adherence(response, gold)
        assert result.score == 1.0

    def test_multi_step_partial(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "params": {}}],
        }
        gold = {
            "operation_class": "multi_step",
            "steps": [
                {"operation_type": "create_primitive"},
                {"operation_type": "transform"},
            ],
        }
        result = instruction_adherence(response, gold)
        assert result.score == 0.5

    def test_invalid_correctly_rejected(self):
        response = {"status": "error", "operations": [], "warnings": ["Negative dimension"]}
        gold = {
            "operation_class": "invalid",
            "expected_behavior": "reject_with_explanation",
        }
        result = instruction_adherence(response, gold)
        assert result.score == 1.0

    def test_invalid_wrongly_accepted(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "params": {}}],
        }
        gold = {
            "operation_class": "invalid",
            "expected_behavior": "reject_with_explanation",
        }
        result = instruction_adherence(response, gold)
        assert result.score == 0.0

    def test_ambiguous_clarification_requested(self):
        response = {"status": "clarification_needed", "operations": []}
        gold = {
            "operation_class": "ambiguous",
            "expected_behavior": "request_clarification",
        }
        result = instruction_adherence(response, gold)
        assert result.score == 1.0

    def test_ambiguous_defaults_with_assumptions(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "params": {}}],
            "assumptions": ["Assumed standard residential height of 3m per floor"],
        }
        gold = {
            "operation_class": "ambiguous",
            "expected_behavior": "infer_and_explain",
        }
        result = instruction_adherence(response, gold)
        assert result.score == 1.0

    def test_ambiguous_defaults_without_assumptions(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "params": {}}],
        }
        gold = {
            "operation_class": "ambiguous",
            "expected_behavior": "infer_and_explain",
        }
        result = instruction_adherence(response, gold)
        assert result.score == 0.5


# ── Geometry Validity ─────────────────────────────────────────────────────

class TestGeometryValidity:
    """Tests for geometry_validity metric."""

    def test_all_params_correct(self):
        response = {
            "status": "success",
            "operations": [
                {"type": "create_primitive", "params": {"width": 5.0, "height": 3.0, "depth": 4.0}}
            ],
        }
        gold = {
            "operation_class": "create_primitive",
            "required_params": ["width", "height", "depth"],
            "expected_values": {"width": 5.0, "height": 3.0, "depth": 4.0},
        }
        result = geometry_validity(response, gold)
        assert result.score == 1.0

    def test_missing_param(self):
        response = {
            "status": "success",
            "operations": [
                {"type": "create_primitive", "params": {"width": 5.0, "height": 3.0}}
            ],
        }
        gold = {
            "operation_class": "create_primitive",
            "required_params": ["width", "height", "depth"],
            "expected_values": {"width": 5.0, "height": 3.0, "depth": 4.0},
        }
        result = geometry_validity(response, gold)
        assert result.score < 1.0

    def test_wrong_value(self):
        response = {
            "status": "success",
            "operations": [
                {"type": "create_primitive", "params": {"width": 10.0, "height": 3.0, "depth": 4.0}}
            ],
        }
        gold = {
            "operation_class": "create_primitive",
            "required_params": ["width", "height", "depth"],
            "expected_values": {"width": 5.0, "height": 3.0, "depth": 4.0},
        }
        result = geometry_validity(response, gold)
        assert result.score < 1.0

    def test_no_operations(self):
        response = {"status": "error", "operations": []}
        gold = {"operation_class": "create_primitive", "required_params": ["width"]}
        result = geometry_validity(response, gold)
        assert result.score == 0.0

    def test_invalid_prompt_correct_rejection(self):
        response = {"status": "error", "operations": []}
        gold = {"operation_class": "invalid"}
        result = geometry_validity(response, gold)
        assert result.score == 1.0


# ── Hallucination Rate ────────────────────────────────────────────────────

class TestHallucinationRate:
    """Tests for hallucination_rate metric."""

    def test_no_extra_ops(self):
        response = {
            "operations": [{"type": "create_primitive", "params": {}}],
        }
        gold = {"operation_class": "create_primitive", "operation_type": "box"}
        result = hallucination_rate(response, gold)
        assert result.score == 1.0

    def test_extra_ops(self):
        response = {
            "operations": [
                {"type": "create_primitive", "params": {}},
                {"type": "transform", "params": {}},
                {"type": "pattern", "params": {}},
            ],
        }
        gold = {"operation_class": "create_primitive", "operation_type": "box"}
        result = hallucination_rate(response, gold)
        assert result.score < 1.0

    def test_no_operations(self):
        response = {"operations": []}
        gold = {"operation_class": "create_primitive"}
        result = hallucination_rate(response, gold)
        assert result.score == 1.0  # No hallucination possible

    def test_invalid_with_operations(self):
        response = {"operations": [{"type": "create_primitive", "params": {}}]}
        gold = {"operation_class": "invalid"}
        result = hallucination_rate(response, gold)
        assert result.score == 0.0


# ── Consistency ───────────────────────────────────────────────────────────

class TestConsistency:
    """Tests for consistency metric."""

    def test_identical_responses(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "subtype": "box", "params": {"width": 5}}],
        }
        result = consistency([response, response, response], {})
        assert result.score == 1.0

    def test_different_statuses(self):
        r1 = {"status": "success", "operations": [{"type": "a", "subtype": "b", "params": {}}]}
        r2 = {"status": "error", "operations": []}
        result = consistency([r1, r2], {})
        assert result.score < 1.0

    def test_single_response(self):
        response = {"status": "success", "operations": []}
        result = consistency([response], {})
        assert result.score == 1.0


# ── Recovery Behavior ─────────────────────────────────────────────────────

class TestRecoveryBehavior:
    """Tests for recovery_behavior metric."""

    def test_non_adversarial_prompt(self):
        response = {"status": "success"}
        gold = {"operation_class": "create_primitive"}
        result = recovery_behavior(response, gold)
        assert result.score == 1.0  # N/A

    def test_correct_rejection_with_warning(self):
        response = {
            "status": "error",
            "operations": [],
            "warnings": ["Negative dimensions are not allowed"],
        }
        gold = {
            "operation_class": "invalid",
            "expected_behavior": "reject_with_explanation",
            "error_type": "invalid_param_value",
        }
        result = recovery_behavior(response, gold)
        assert result.score == 1.0

    def test_accepted_invalid_with_geometry(self):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "params": {"width": -5}}],
            "warnings": [],
        }
        gold = {
            "operation_class": "invalid",
            "expected_behavior": "reject_with_explanation",
            "error_type": "invalid_param_value",
        }
        result = recovery_behavior(response, gold)
        assert result.score < 0.5
