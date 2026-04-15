"""
Google Gemini LLM adapter.

Wraps the Google GenAI (Gemini) API with retry logic, structured JSON output
parsing, and latency tracking.  Exposes a single ``generate()`` method consumed
by the runner.
"""

from __future__ import annotations

import json
import re
import time
import logging
from typing import Any

from google import genai
from google.genai import errors as genai_errors

from src.config import LlmConfig

logger = logging.getLogger(__name__)


class GeminiAdapter:
    """Thin wrapper around the Google Gemini API."""

    def __init__(self, config: LlmConfig) -> None:
        config.validate()
        self._client = genai.Client(api_key=config.api_key)
        self._model = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        retries: int = 5,
        expect_json: bool = True,
    ) -> dict[str, Any]:
        """
        Send a prompt to Gemini and return parsed results.

        Parameters
        ----------
        system_prompt : str
            The system-level instruction (prompt template).
        user_prompt : str
            The user's natural-language geometry request.
        retries : int
            Number of retry attempts on transient failures.
        expect_json : bool
            If True, attempt to parse the assistant's response as JSON.

        Returns
        -------
        dict with keys:
            - ``raw_response``  : str   – the full assistant message
            - ``parsed``        : dict | None – parsed JSON (if expect_json)
            - ``latency_ms``    : float – round-trip time in milliseconds
            - ``model``         : str   – model used
            - ``error``         : str | None – error message if any
        """
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                return self._call(system_prompt, user_prompt, expect_json)
            except genai_errors.ClientError as exc:
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                    # Parse retry delay from Gemini response if available
                    wait = self._parse_retry_delay(str(exc)) or min(30 * attempt, 120)
                    logger.warning(
                        "Rate limited (attempt %d/%d) — retrying in %ds",
                        attempt, retries, wait,
                    )
                    last_error = str(exc)
                    time.sleep(wait)
                else:
                    logger.error("Non-retryable API error: %s", exc)
                    return {
                        "raw_response": "",
                        "parsed": None,
                        "latency_ms": 0.0,
                        "model": self._model,
                        "error": str(exc),
                    }
            except Exception as exc:
                logger.error("Unexpected error: %s", exc)
                return {
                    "raw_response": "",
                    "parsed": None,
                    "latency_ms": 0.0,
                    "model": self._model,
                    "error": str(exc),
                }

        return {
            "raw_response": "",
            "parsed": None,
            "latency_ms": 0.0,
            "model": self._model,
            "error": "Exhausted %d retries. Last error: %s" % (retries, last_error),
        }

    @staticmethod
    def _parse_retry_delay(error_msg: str) -> int:
        """Extract retry delay from Gemini error message (e.g. 'retry in 57.12s')."""
        match = re.search(r'retryDelay["\']?:\s*["\']?(\d+)', error_msg)
        if match:
            return int(match.group(1)) + 2  # Add buffer
        match = re.search(r'retry in (\d+)', error_msg)
        if match:
            return int(match.group(1)) + 2
        return 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(
        self, system_prompt: str, user_prompt: str, expect_json: bool
    ) -> dict[str, Any]:
        start = time.perf_counter()

        config = {
            "temperature": self._temperature,
            "max_output_tokens": self._max_tokens,
        }
        if expect_json:
            config["response_mime_type"] = "application/json"

        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                **config,
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        raw = response.text or ""
        parsed = None
        error = None

        if expect_json:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                error = "JSON parse error: %s" % exc
                logger.warning("Failed to parse JSON response: %s", raw[:200])

        return {
            "raw_response": raw,
            "parsed": parsed,
            "latency_ms": round(elapsed_ms, 1),
            "model": self._model,
            "error": error,
        }
