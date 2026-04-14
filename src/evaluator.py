"""
Evaluator — scores a set of LLM responses against gold expectations.

Orchestrates metric computation across all prompts and aggregates results
into per-category and overall scores. Also classifies failures into a
taxonomy for the final report.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.metrics import (
    MetricResult,
    instruction_adherence,
    geometry_validity,
    hallucination_rate,
    consistency,
    recovery_behavior,
)

logger = logging.getLogger(__name__)


# ── Failure Taxonomy ──────────────────────────────────────────────────────

FAILURE_TYPES = {
    "missing_params": "Required parameters absent from output",
    "wrong_operation": "Operation type does not match expected class",
    "hallucinated_extra": "Output contains unrequested operations",
    "invalid_range": "Parameter values outside valid range",
    "refused_valid": "Model refused a valid, clear request",
    "accepted_invalid": "Model accepted an invalid or adversarial request",
    "inconsistent_output": "Repeated runs produced different results",
    "no_explanation": "Model failed to explain assumptions or errors",
    "schema_violation": "Output did not match expected JSON schema",
}


@dataclass
class PromptEvaluation:
    """Evaluation result for a single prompt."""

    prompt_id: str
    category: str
    difficulty: str
    prompt_text: str
    metrics: dict[str, MetricResult] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    raw_responses: list[dict[str, Any]] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        """Average of all metric scores."""
        scores = [m.score for m in self.metrics.values()]
        return round(sum(scores) / len(scores), 3) if scores else 0.0


@dataclass
class EvaluationReport:
    """Aggregated evaluation report across all prompts."""

    template_version: str
    model: str
    evaluations: list[PromptEvaluation] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        scores = [e.overall_score for e in self.evaluations]
        return round(sum(scores) / len(scores), 3) if scores else 0.0

    def by_category(self) -> dict[str, float]:
        """Average score per category (normal/ambiguous/adversarial)."""
        buckets: dict[str, list[float]] = {}
        for e in self.evaluations:
            buckets.setdefault(e.category, []).append(e.overall_score)
        return {k: round(sum(v) / len(v), 3) for k, v in buckets.items()}

    def by_metric(self) -> dict[str, float]:
        """Average score per metric name."""
        buckets: dict[str, list[float]] = {}
        for e in self.evaluations:
            for name, m in e.metrics.items():
                buckets.setdefault(name, []).append(m.score)
        return {k: round(sum(v) / len(v), 3) for k, v in buckets.items()}

    def failure_taxonomy(self) -> dict[str, int]:
        """Count of each failure type across all evaluations."""
        counts: dict[str, int] = {}
        for e in self.evaluations:
            for f in e.failures:
                counts[f] = counts.get(f, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def by_difficulty(self) -> dict[str, float]:
        """Average score per difficulty level."""
        buckets: dict[str, list[float]] = {}
        for e in self.evaluations:
            buckets.setdefault(e.difficulty, []).append(e.overall_score)
        return {k: round(sum(v) / len(v), 3) for k, v in buckets.items()}


class Evaluator:
    """Scores LLM responses against gold expectations."""

    def __init__(self, gold_path: Path) -> None:
        with open(gold_path) as f:
            self._gold: dict[str, Any] = json.load(f)

    def evaluate_prompt(
        self,
        prompt_id: str,
        category: str,
        difficulty: str,
        prompt_text: str,
        responses: list[dict[str, Any]],
    ) -> PromptEvaluation:
        """
        Evaluate one prompt's responses against its gold expectation.

        Parameters
        ----------
        prompt_id : str
            The prompt ID (e.g., "N01").
        category : str
            Category: "normal", "ambiguous", or "adversarial".
        difficulty : str
            Difficulty level: "easy", "medium", "hard", "edge".
        prompt_text : str
            The raw prompt text.
        responses : list[dict]
            One or more parsed JSON responses from the LLM.
        """
        gold = self._gold.get(prompt_id)
        if gold is None:
            logger.warning("No gold expectation for prompt %s", prompt_id)
            return PromptEvaluation(
                prompt_id=prompt_id,
                category=category,
                difficulty=difficulty,
                prompt_text=prompt_text,
            )

        primary = responses[0] if responses else {}
        eval_result = PromptEvaluation(
            prompt_id=prompt_id,
            category=category,
            difficulty=difficulty,
            prompt_text=prompt_text,
            raw_responses=responses,
        )

        # ── Run metrics ──
        eval_result.metrics["instruction_adherence"] = instruction_adherence(primary, gold)
        eval_result.metrics["geometry_validity"] = geometry_validity(primary, gold)
        eval_result.metrics["hallucination_rate"] = hallucination_rate(primary, gold)
        eval_result.metrics["consistency"] = consistency(responses, gold)
        eval_result.metrics["recovery_behavior"] = recovery_behavior(primary, gold)

        # ── Classify failures ──
        eval_result.failures = self._classify_failures(eval_result.metrics, primary, gold)

        return eval_result

    def evaluate_all(
        self,
        results: dict[str, dict[str, Any]],
        template_version: str,
        model: str,
    ) -> EvaluationReport:
        """
        Evaluate all prompts and produce an aggregated report.

        Parameters
        ----------
        results : dict
            Mapping of prompt_id → {category, difficulty, prompt_text, responses: [...]}
        template_version : str
            Which prompt template was used (v1/v2/v3).
        model : str
            LLM model identifier.
        """
        report = EvaluationReport(template_version=template_version, model=model)

        for prompt_id, data in results.items():
            evaluation = self.evaluate_prompt(
                prompt_id=prompt_id,
                category=data["category"],
                difficulty=data["difficulty"],
                prompt_text=data["prompt_text"],
                responses=data["responses"],
            )
            report.evaluations.append(evaluation)

        return report

    # ── Failure Classification ────────────────────────────────────────────

    @staticmethod
    def _classify_failures(
        metrics: dict[str, MetricResult],
        response: dict[str, Any],
        gold: dict[str, Any],
    ) -> list[str]:
        """Classify observed failures into the taxonomy."""
        failures: list[str] = []

        adherence = metrics.get("instruction_adherence")
        validity = metrics.get("geometry_validity")
        hallucination = metrics.get("hallucination_rate")
        consist = metrics.get("consistency")
        recovery = metrics.get("recovery_behavior")

        if adherence and adherence.score < 1.0:
            gold_class = gold.get("operation_class", "")
            if gold_class == "invalid" and response.get("status") == "success":
                failures.append("accepted_invalid")
            elif gold_class != "invalid" and response.get("status") == "error":
                failures.append("refused_valid")
            else:
                failures.append("wrong_operation")

        if validity and validity.score < 1.0:
            details = validity.details.get("issues", [])
            if any("missing" in str(d).lower() for d in details):
                failures.append("missing_params")
            if any("expected" in str(d).lower() for d in details):
                failures.append("invalid_range")

        if hallucination and hallucination.score < 1.0:
            failures.append("hallucinated_extra")

        if consist and consist.score < 0.9:
            failures.append("inconsistent_output")

        if recovery and recovery.score < 1.0 and gold.get("operation_class") == "invalid":
            if not response.get("warnings") and not response.get("clarification_request"):
                failures.append("no_explanation")

        # Schema violations
        if response.get("status") not in ("success", "error", "clarification_needed", None, ""):
            failures.append("schema_violation")
        if response.get("status") == "success" and not isinstance(response.get("operations"), list):
            failures.append("schema_violation")

        return list(set(failures))  # deduplicate
