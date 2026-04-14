"""
Tests for the evaluator module.

Validates the Evaluator class, PromptEvaluation, EvaluationReport,
and failure classification logic.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.evaluator import Evaluator, PromptEvaluation, EvaluationReport


@pytest.fixture
def gold_path(tmp_path: Path) -> Path:
    """Create a temporary gold expectations file."""
    gold = {
        "T01": {
            "operation_class": "create_primitive",
            "operation_type": "box",
            "required_params": ["width", "height", "depth"],
            "expected_values": {"width": 5.0, "height": 3.0, "depth": 4.0},
            "unit": "meters",
            "constraints": [],
            "valid_response": True,
        },
        "T02": {
            "operation_class": "invalid",
            "expected_behavior": "reject_with_explanation",
            "error_type": "invalid_param_value",
            "constraints": ["negative_dimension"],
            "valid_response": False,
        },
        "T03": {
            "operation_class": "ambiguous",
            "expected_behavior": "request_clarification",
            "constraints": ["should_ask_for_dimensions"],
            "valid_response": True,
        },
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(gold))
    return path


@pytest.fixture
def evaluator(gold_path: Path) -> Evaluator:
    return Evaluator(gold_path)


class TestEvaluator:
    """Tests for the Evaluator class."""

    def test_evaluate_correct_normal_prompt(self, evaluator: Evaluator):
        response = {
            "status": "success",
            "operations": [
                {
                    "type": "create_primitive",
                    "subtype": "box",
                    "params": {"width": 5.0, "height": 3.0, "depth": 4.0},
                }
            ],
            "warnings": [],
        }
        result = evaluator.evaluate_prompt(
            prompt_id="T01",
            category="normal",
            difficulty="easy",
            prompt_text="Create a box 5x3x4",
            responses=[response],
        )
        assert result.overall_score > 0.8
        assert len(result.failures) == 0

    def test_evaluate_invalid_correctly_rejected(self, evaluator: Evaluator):
        response = {
            "status": "error",
            "operations": [],
            "warnings": ["Negative dimension not allowed"],
        }
        result = evaluator.evaluate_prompt(
            prompt_id="T02",
            category="adversarial",
            difficulty="edge",
            prompt_text="Create a box with width -5",
            responses=[response],
        )
        assert result.metrics["instruction_adherence"].score == 1.0
        assert result.metrics["recovery_behavior"].score == 1.0

    def test_evaluate_ambiguous_with_clarification(self, evaluator: Evaluator):
        response = {
            "status": "clarification_needed",
            "operations": [],
            "clarification_request": "What dimensions would you like?",
        }
        result = evaluator.evaluate_prompt(
            prompt_id="T03",
            category="ambiguous",
            difficulty="easy",
            prompt_text="Make a building",
            responses=[response],
        )
        assert result.metrics["instruction_adherence"].score == 1.0

    def test_missing_gold_expectation(self, evaluator: Evaluator):
        result = evaluator.evaluate_prompt(
            prompt_id="UNKNOWN",
            category="normal",
            difficulty="easy",
            prompt_text="Create something",
            responses=[{}],
        )
        assert len(result.metrics) == 0

    def test_failure_classification_accepted_invalid(self, evaluator: Evaluator):
        response = {
            "status": "success",
            "operations": [{"type": "create_primitive", "params": {"width": -5}}],
        }
        result = evaluator.evaluate_prompt(
            prompt_id="T02",
            category="adversarial",
            difficulty="edge",
            prompt_text="Create a box with width -5",
            responses=[response],
        )
        assert "accepted_invalid" in result.failures


class TestEvaluationReport:
    """Tests for the EvaluationReport class."""

    def test_overall_score(self):
        report = EvaluationReport(template_version="v1", model="test")
        e1 = PromptEvaluation("P1", "normal", "easy", "test1")
        from src.metrics import MetricResult
        e1.metrics = {"m1": MetricResult("m1", 0.8, ""), "m2": MetricResult("m2", 0.6, "")}
        e2 = PromptEvaluation("P2", "normal", "easy", "test2")
        e2.metrics = {"m1": MetricResult("m1", 1.0, ""), "m2": MetricResult("m2", 1.0, "")}
        report.evaluations = [e1, e2]

        assert report.overall_score == pytest.approx(0.85, abs=0.01)

    def test_by_category(self):
        report = EvaluationReport(template_version="v1", model="test")
        from src.metrics import MetricResult

        e1 = PromptEvaluation("P1", "normal", "easy", "test1")
        e1.metrics = {"m1": MetricResult("m1", 1.0, "")}
        e2 = PromptEvaluation("P2", "ambiguous", "easy", "test2")
        e2.metrics = {"m1": MetricResult("m1", 0.5, "")}
        report.evaluations = [e1, e2]

        cats = report.by_category()
        assert cats["normal"] == 1.0
        assert cats["ambiguous"] == 0.5

    def test_failure_taxonomy(self):
        report = EvaluationReport(template_version="v1", model="test")
        e1 = PromptEvaluation("P1", "normal", "easy", "test1", failures=["missing_params", "wrong_operation"])
        e2 = PromptEvaluation("P2", "normal", "easy", "test2", failures=["missing_params"])
        report.evaluations = [e1, e2]

        taxonomy = report.failure_taxonomy()
        assert taxonomy["missing_params"] == 2
        assert taxonomy["wrong_operation"] == 1

    def test_empty_report(self):
        report = EvaluationReport(template_version="v1", model="test")
        assert report.overall_score == 0.0
        assert report.by_category() == {}
        assert report.failure_taxonomy() == {}
