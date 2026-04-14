"""
Runner — executes all prompts in the corpus against a given template version.

Handles:
  - Loading the prompt corpus from CSV
  - Loading the prompt template
  - Sending each prompt to the LLM
  - Collecting responses (with consistency re-runs)
  - Feeding results to the Evaluator
"""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.config import LlmConfig, EvalConfig, TEMPLATES_DIR, PROMPTS_DIR
from src.models.openai_adapter import OpenAIAdapter
from src.evaluator import Evaluator, EvaluationReport

logger = logging.getLogger(__name__)


class Runner:
    """Orchestrates prompt evaluation runs."""

    def __init__(
        self,
        llm_config: LlmConfig,
        eval_config: EvalConfig,
    ) -> None:
        self._llm = OpenAIAdapter(llm_config)
        self._eval_config = eval_config
        self._evaluator = Evaluator(eval_config.gold_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, template_version: str) -> EvaluationReport:
        """
        Execute the full evaluation pipeline for a template version.

        Parameters
        ----------
        template_version : str
            One of "v1", "v2", "v3" — maps to the template file.

        Returns
        -------
        EvaluationReport
            The complete evaluation report with scores and failures.
        """
        system_prompt = self._load_template(template_version)
        corpus = self._load_corpus()
        results: dict[str, dict[str, Any]] = {}
        total = len(corpus)

        logger.info(
            "Starting evaluation: template=%s, prompts=%d, consistency_runs=%d",
            template_version, total, self._eval_config.consistency_runs,
        )

        for i, row in enumerate(corpus, 1):
            prompt_id = row["id"]
            prompt_text = row["prompt"]
            category = row["category"]
            difficulty = row["difficulty"]

            logger.info("[%d/%d] Evaluating %s: %s", i, total, prompt_id, prompt_text[:60])

            responses = self._run_prompt(
                system_prompt=system_prompt,
                user_prompt=prompt_text,
                runs=self._eval_config.consistency_runs,
            )

            results[prompt_id] = {
                "category": category,
                "difficulty": difficulty,
                "prompt_text": prompt_text,
                "responses": responses,
            }

            # Rate-limit courtesy pause
            time.sleep(0.5)

        report = self._evaluator.evaluate_all(
            results=results,
            template_version=template_version,
            model=self._llm._model,
        )

        logger.info(
            "Evaluation complete: overall=%.1f%%, prompts=%d",
            report.overall_score * 100, total,
        )
        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_template(self, version: str) -> str:
        """Load a system prompt template by version name."""
        version_map = {
            "v1": "v1_baseline.txt",
            "v2": "v2_structured.txt",
            "v3": "v3_cot.txt",
        }
        filename = version_map.get(version)
        if not filename:
            raise ValueError(f"Unknown template version: {version}. Use v1, v2, or v3.")

        path = TEMPLATES_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")

        return path.read_text(encoding="utf-8").strip()

    def _load_corpus(self) -> list[dict[str, str]]:
        """Load the prompt corpus from CSV."""
        path = self._eval_config.corpus_path
        if not path.exists():
            raise FileNotFoundError(f"Corpus not found: {path}")

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        logger.info("Loaded %d prompts from corpus", len(rows))
        return rows

    def _run_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        runs: int,
    ) -> list[dict[str, Any]]:
        """
        Run a single prompt through the LLM, optionally multiple times
        for consistency measurement.
        """
        responses: list[dict[str, Any]] = []

        for run_idx in range(runs):
            result = self._llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                expect_json=True,
            )

            if result["error"]:
                logger.warning(
                    "LLM error on run %d: %s", run_idx + 1, result["error"]
                )
                # Use a structured error response for evaluation
                parsed = {
                    "status": "error",
                    "operations": [],
                    "warnings": [result["error"]],
                    "error": result["error"],
                }
            else:
                parsed = result["parsed"] or {
                    "status": "error",
                    "operations": [],
                    "warnings": ["Failed to parse LLM response"],
                }

            # Attach metadata
            parsed["_meta"] = {
                "run_index": run_idx,
                "latency_ms": result["latency_ms"],
                "model": result["model"],
                "raw_response": result["raw_response"][:500],
            }

            responses.append(parsed)

        return responses
